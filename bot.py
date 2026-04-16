import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, SCRAPE_INTERVAL_MINUTES, MAX_NEWS_PER_RADAR
from db import (
    init_db, save_news, get_top_news, mark_as_tweeted,
    save_pending_tweet, get_pending_tweet, update_tweet_status,
)
from scraper import run_scraper
from generator import enrich_radar, generate_tweet
from publisher import post_tweet

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

TZ_SP = ZoneInfo("America/Sao_Paulo")
_last_radar: dict = {}


# ─────────────────────────────────────────────
# RADAR CYCLE
# ─────────────────────────────────────────────
async def run_radar_cycle(app: Application):
    logger.info("Iniciando ciclo do radar...")
    try:
        items     = await run_scraper()
        new_count = save_news(items)
        if new_count == 0:
            logger.info("Nenhuma notícia nova.")
            return

        top = get_top_news(limit=MAX_NEWS_PER_RADAR)
        if not top:
            return

        top_dicts = [
            {"id": r[0], "title": r[1], "url": r[2], "source": r[3],
             "published_at": r[4], "score": r[5], "image_url": r[6]}
            for r in top
        ]

        logger.info(f"Enriquecendo {len(top_dicts)} itens...")
        enriched = enrich_radar(top_dicts)

        msg = await _send_radar(app, enriched)
        _last_radar[msg.message_id] = enriched
        if len(_last_radar) > 3:
            del _last_radar[min(_last_radar.keys())]

    except Exception as e:
        logger.error(f"Erro no radar: {e}", exc_info=True)


async def _send_radar(app: Application, items: list):
    # Hora em São Paulo (não UTC)
    now_sp = datetime.now(TZ_SP).strftime("%d/%m %H:%M")
    lines  = [f"🔍 *RADAR — PARLAPALESTRINO*", f"`{now_sp} (Brasília)`\n"]

    for idx, it in enumerate(items, 1):
        dot      = "🟢" if idx <= 2 else "🟡"
        label    = it.get("rotulo", "📌 CONTEXTO")
        title    = it.get("titulo_curto") or it["title"][:70]
        o_que    = it.get("o_que_e", "")
        impacto  = it.get("por_que_importa", "")
        is_rumor = it.get("is_rumor", False)
        has_img  = "🖼️" if it.get("image_url") else ""
        age_str  = _age_str(it["published_at"])

        block = [f"{dot} *C{idx}) {label}*", title]
        if o_que:    block.append(f"🧩 {o_que}")
        if impacto:  block.append(f"⚡️ {impacto}")
        if is_rumor: block.append(f"⚠️ _Ainda não confirmado_")
        block.append(f"📰 {it['source']} · {age_str} {has_img}")
        lines.append("\n".join(block))

    lines.append("\n_Responda com C1, C2... para gerar tweet (ex: `C1` ou `C1,C3`)_")

    text = "\n\n".join(lines)
    if len(text) > 4000:
        text = text[:3950] + "\n\n_[truncado]_"

    return await app.bot.send_message(
        chat_id=TELEGRAM_CHAT_ID,
        text=text,
        parse_mode="Markdown",
        disable_web_page_preview=True,
    )


# ─────────────────────────────────────────────
# HANDLERS DE MENSAGEM
# ─────────────────────────────────────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("editing_tweet_id"):
        await _handle_edit_input(update, context)
        return
    if _is_selection(update.message.text.strip()):
        await _handle_selection(update, context)


def _is_selection(text: str) -> bool:
    cleaned = text.upper().replace("C","").replace(",","").replace(" ","")
    return cleaned.isdigit()


def _parse_selection(text: str, items: list) -> list:
    text = text.upper().replace("C","")
    try:
        return [items[i-1] for i in [int(x.strip()) for x in text.split(",")] if 1 <= i <= len(items)]
    except Exception:
        return []


async def _handle_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _last_radar:
        await update.message.reply_text("Nenhum radar ativo. Use /radar.")
        return

    items    = _last_radar[max(_last_radar.keys())]
    selected = _parse_selection(update.message.text, items)

    if not selected:
        await update.message.reply_text(f"Seleção inválida. Use C1..C{len(items)}.")
        return

    thinking = await update.message.reply_text("✍️ Gerando opções de tweet...")

    titles    = [it["title"] for it in selected]
    news_ids  = [it["id"] for it in selected]
    image_url = next((it.get("image_url") for it in selected if it.get("image_url")), None)
    options   = generate_tweet(titles)

    await thinking.delete()

    if not options:
        await update.message.reply_text("Erro ao gerar tweet. Tente novamente.")
        return

    if image_url:
        try:
            await update.message.reply_photo(
                photo=image_url,
                caption="🖼️ *Imagem que será postada junto*",
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.warning(f"Preview de imagem falhou: {e}")
            image_url = None

    labels = {0: "[A] Informativa", 1: "[B] Engajamento", 2: "[C] Explicador"}

    for i, opt in enumerate(options):
        pending_id = save_pending_tweet(news_ids, opt, image_url)
        chars      = len(opt)
        warn       = " ⚠️" if chars > 270 else ""
        img_badge  = " 🖼️" if image_url else ""

        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(f"✅ Postar{img_badge}", callback_data=f"post:{pending_id}"),
            InlineKeyboardButton("✏️ Editar",             callback_data=f"edit:{pending_id}"),
            InlineKeyboardButton("🗑 Descartar",           callback_data=f"discard:{pending_id}"),
        ]])

        await update.message.reply_text(
            f"*{labels.get(i,f'Opção {i+1}')}* ({chars}/280{warn}{img_badge}):\n\n{opt}",
            parse_mode="Markdown",
            reply_markup=keyboard,
        )


async def _handle_edit_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pending_id = context.user_data.pop("editing_tweet_id")
    new_text   = update.message.text.strip()
    if len(new_text) > 280:
        await update.message.reply_text(f"❌ {len(new_text)}/280. Tente de novo:")
        context.user_data["editing_tweet_id"] = pending_id
        return

    row = get_pending_tweet(pending_id)
    if not row:
        await update.message.reply_text("Tweet expirou. Use /radar.")
        return

    _, news_ids_str, _, old_image = row
    news_ids       = [int(x) for x in news_ids_str.split(",")]
    new_pending_id = save_pending_tweet(news_ids, new_text, old_image)
    update_tweet_status(pending_id, "discarded")

    img_badge = " 🖼️" if old_image else ""
    keyboard  = InlineKeyboardMarkup([[
        InlineKeyboardButton(f"✅ Postar{img_badge}", callback_data=f"post:{new_pending_id}"),
    ]])
    await update.message.reply_text(
        f"*Preview ({len(new_text)}/280{img_badge}):*\n\n{new_text}",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


# ─────────────────────────────────────────────
# CALLBACKS
# ─────────────────────────────────────────────
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action, pid_str = query.data.split(":", 1)
    pid = int(pid_str)

    if action == "post":
        await _do_post(query, pid)
    elif action == "edit":
        row = get_pending_tweet(pid)
        if not row:
            await query.edit_message_text("Tweet já processado.")
            return
        _, _, tweet_text, _ = row
        context.user_data["editing_tweet_id"] = pid
        await query.edit_message_text(
            f"✏️ *Edição ativa.* Envie o novo texto (max 280):\n\n`{tweet_text}`",
            parse_mode="Markdown",
        )
    elif action == "discard":
        update_tweet_status(pid, "discarded")
        await query.edit_message_text("🗑 Descartado.")


async def _do_post(query, pid: int):
    row = get_pending_tweet(pid)
    if not row:
        await query.edit_message_text("Tweet já processado ou expirou.")
        return

    _, news_ids_str, tweet_text, image_url = row
    img_info = "com imagem 🖼️" if image_url else "sem imagem"
    await query.edit_message_text(f"⏳ Publicando {img_info}...")

    result = post_tweet(tweet_text, image_url)

    if result["success"]:
        for nid in news_ids_str.split(","):
            mark_as_tweeted(int(nid))
        update_tweet_status(pid, "posted")
        img_label = " + imagem 🖼️" if result.get("with_image") else ""
        await query.edit_message_text(
            f"✅ *Publicado{img_label}!*\n\n{tweet_text}\n\n🔗 {result['url']}",
            parse_mode="Markdown",
        )
    else:
        await query.edit_message_text(
            f"❌ Falha: `{result['error']}`\n\n{tweet_text}",
            parse_mode="Markdown",
        )


# ─────────────────────────────────────────────
# COMANDOS
# ─────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🌿 *ParlaPalestrino Bot* no ar!\n\n"
        "/radar — busca notícias agora\n"
        "/status — últimas notícias no banco\n"
        "/diagnostico — verifica saúde do sistema\n"
        "/twitter\\_setup — configura busca no Twitter",
        parse_mode="Markdown",
    )


async def cmd_radar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🔄 Buscando e analisando...")
    await run_radar_cycle(context.application)
    await msg.delete()


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    top = get_top_news(limit=5)
    if not top:
        await update.message.reply_text("Nenhuma notícia. Use /radar.")
        return
    lines = ["📊 *Últimas no banco:*\n"]
    for _, title, _, source, _, score, img in top:
        short = title[:55] + "..." if len(title) > 55 else title
        lines.append(f"• [{score}pts] {'🖼️' if img else '  '} {short}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_diagnostico(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Verifica o status de cada componente do sistema."""
    lines = ["🔧 *Diagnóstico do Sistema*\n"]

    # 1. Banco de dados
    try:
        top = get_top_news(limit=1)
        lines.append("✅ Banco de dados: OK")
    except Exception as e:
        lines.append(f"❌ Banco de dados: {e}")

    # 2. RSS feeds
    try:
        import feedparser
        feed = feedparser.parse("https://ge.globo.com/rss/feed/palmeiras.xml")
        count = len(feed.entries)
        lines.append(f"✅ RSS (GE): {count} entradas")
    except Exception as e:
        lines.append(f"❌ RSS: {e}")

    # 3. twscrape / conta Twitter
    try:
        from twscrape import API as TwAPI
        from config import TWSCRAPE_DB
        api      = TwAPI(TWSCRAPE_DB)
        accounts = await api.pool.get_all()
        if not accounts:
            lines.append("⚠️ Twitter: nenhuma conta configurada — use /twitter_setup")
        else:
            active = [a for a in accounts if a.active]
            lines.append(f"{'✅' if active else '⚠️'} Twitter: {len(accounts)} conta(s), {len(active)} ativa(s)")
            for a in accounts:
                reqs = getattr(a, 'total_req', getattr(a, 'req_count', '?'))
                lines.append(f"   • @{a.username} — {'ativa ✅' if a.active else 'inativa ❌'} — reqs: {reqs}")
    except Exception as e:
        lines.append(f"❌ Twitter (twscrape): {e}")

    # 4. AI (Groq)
    try:
        from openai import OpenAI
        from config import GROQ_API_KEY, GROQ_MODEL
        client = OpenAI(api_key=GROQ_API_KEY, base_url="https://api.groq.com/openai/v1")
        resp   = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role":"user","content":"Responda só: OK"}],
            max_tokens=5,
        )
        lines.append(f"✅ AI (Groq/{GROQ_MODEL}): OK")
    except Exception as e:
        lines.append(f"❌ AI (Groq): {e}")

    # 5. Hora local
    now_sp = datetime.now(TZ_SP).strftime("%d/%m/%Y %H:%M:%S")
    lines.append(f"\n🕐 Hora em São Paulo: `{now_sp}`")

    await update.message.reply_text("\n".join(lines))


async def cmd_twitter_setup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Configura e testa o login da conta scraper no Twitter."""
    from twscrape import API as TwAPI
    from config import (
        TWSCRAPE_DB, SCRAPER_TWITTER_USER, SCRAPER_TWITTER_PASS,
        SCRAPER_TWITTER_EMAIL, SCRAPER_TWITTER_EMAIL_PASS,
    )

    msg = await update.message.reply_text("🔄 Verificando conta do Twitter scraper...")

    try:
        api      = TwAPI(TWSCRAPE_DB)
        accounts = await api.pool.get_all()

        if not accounts:
            await msg.edit_text(f"➕ Adicionando conta @{SCRAPER_TWITTER_USER}...")
            await api.pool.add_account(
                username=SCRAPER_TWITTER_USER,
                password=SCRAPER_TWITTER_PASS,
                email=SCRAPER_TWITTER_EMAIL,
                email_password=SCRAPER_TWITTER_EMAIL_PASS,
            )
            accounts = await api.pool.get_all()

        await msg.edit_text(f"🔐 Fazendo login com @{SCRAPER_TWITTER_USER}...\n(pode demorar até 30 segundos)")

        await api.pool.login_all()
        accounts = await api.pool.get_all()
        active   = [a for a in accounts if a.active]

        if active:
            # Testa uma busca real
            await msg.edit_text("🔍 Testando busca 'Palmeiras'...")
            count = 0
            async for tweet in api.search("Palmeiras lang:pt", limit=3):
                count += 1
            await msg.edit_text(
                f"✅ *Twitter configurado!*\n\n"
                f"• Conta: @{SCRAPER_TWITTER_USER}\n"
                f"• Status: ativa\n"
                f"• Teste de busca: {count} tweets encontrados\n\n"
                f"O próximo /radar já vai incluir tweets do X.",
                parse_mode="Markdown",
            )
        else:
            await msg.edit_text(
                f"⚠️ *Login falhou.*\n\n"
                f"Conta @{SCRAPER_TWITTER_USER} não ficou ativa.\n\n"
                f"Verifique:\n"
                f"• Senha correta no .env\n"
                f"• Conta não bloqueada/suspensa\n"
                f"• Email de verificação no inbox de {SCRAPER_TWITTER_EMAIL}",
                parse_mode="Markdown",
            )

    except Exception as e:
        await msg.edit_text(
            f"❌ Erro no setup do Twitter:\n`{e}`\n\n"
            f"Verifique as credenciais no .env e tente novamente.",
            parse_mode="Markdown",
        )


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def _age_str(iso: str) -> str:
    try:
        pub = datetime.fromisoformat(iso.replace("Z","+00:00"))
        if not pub.tzinfo: pub = pub.replace(tzinfo=timezone.utc)
        age = int((datetime.now(timezone.utc)-pub).total_seconds()/60)
        return f"{age}min" if age < 60 else f"{age//60}h"
    except: return "?"


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
def main():
    init_db()
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start",          cmd_start))
    app.add_handler(CommandHandler("help",           cmd_start))
    app.add_handler(CommandHandler("radar",          cmd_radar))
    app.add_handler(CommandHandler("status",         cmd_status))
    app.add_handler(CommandHandler("diagnostico",    cmd_diagnostico))
    app.add_handler(CommandHandler("twitter_setup",  cmd_twitter_setup))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.Chat(TELEGRAM_CHAT_ID),
        handle_message,
    ))

    scheduler = AsyncIOScheduler(timezone="America/Sao_Paulo")
    scheduler.add_job(run_radar_cycle, "interval", minutes=SCRAPE_INTERVAL_MINUTES,
                      args=[app], id="radar_cycle", max_instances=1, coalesce=True)
    scheduler.start()
    logger.info(f"Bot iniciado. Radar a cada {SCRAPE_INTERVAL_MINUTES} min.")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
