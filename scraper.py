import re, json, hashlib, asyncio, feedparser, urllib.request
from datetime import datetime, date, timedelta, timezone
from zoneinfo import ZoneInfo
from twscrape import API as TwAPI
from config import (
    TWSCRAPE_DB, SCRAPER_TWITTER_USER, SCRAPER_TWITTER_PASS,
    SCRAPER_TWITTER_EMAIL, SCRAPER_TWITTER_EMAIL_PASS, NEWS_MAX_AGE_HOURS,
)

TZ_SP = ZoneInfo("America/Sao_Paulo")

RSS_FEEDS = [
    ("Globo Esporte", "https://ge.globo.com/rss/feed/palmeiras.xml"),
    ("Lance",         "https://www.lance.com.br/rss/palmeiras.xml"),
    ("UOL Esporte",   "https://esporte.uol.com.br/futebol/campeonatos/brasileiro/index.rss"),
    ("ESPN Brasil",   "https://www.espn.com.br/rss/futebol/palmeiras.xml"),
    ("Google News",   "https://news.google.com/rss/search?q=Palmeiras+Futebol&hl=pt-BR&gl=BR&ceid=BR:pt-419"),
]

KW_BASE    = ["palmeiras", "verdão", "alviverde"]
KW_PLAYERS = ["estêvão","flaco lopez","abel ferreira","rony","raphael veiga",
               "weverton","murilo","gustavo gómez","naves","facundo torres",
               "mauricio","piquerez","marcos rocha"]
KW_BOOST   = ["contratação","lesão","desfalque","gol","título","copa",
               "libertadores","semifinal","final","campeão","convocado",
               "seleção","demitido","renovação","rescisão","escalação",
               "suspenso","expulso","stjd"]

def _score(t):
    t = t.lower()
    return sum(10 for k in KW_BASE if k in t) + sum(5 for k in KW_PLAYERS if k in t) + sum(3 for k in KW_BOOST if k in t)

def _hash(u): return hashlib.md5(u.encode()).hexdigest()

def _parse_pub(e):
    try:
        if hasattr(e,"published_parsed") and e.published_parsed:
            return datetime(*e.published_parsed[:6], tzinfo=timezone.utc).isoformat()
    except: pass
    return datetime.now(timezone.utc).isoformat()

def _age(iso):
    try:
        pub = datetime.fromisoformat(iso.replace("Z","+00:00"))
        if not pub.tzinfo: pub = pub.replace(tzinfo=timezone.utc)
        return int((datetime.now(timezone.utc)-pub).total_seconds()/60)
    except: return 9999

# ── AGENDA (API oficial Palmeiras) ────────────────────────────────────────────
def _clean_html(s): return re.sub(r"\s+"," ",re.sub(r"<[^>]+>","",s or "")).strip()

def _infer_date(ddmm, ref):
    if not ddmm or "/" not in ddmm: return None
    try:
        d,m = [int(x) for x in ddmm.split("/")]
        y = ref.year + (1 if ref.month==12 and m==1 else 0)
        return date(y,m,d)
    except: return None

def _infer_time(it):
    if it.get("hora1"): return it["hora1"]
    h = (it.get("hora") or "").strip()
    m = re.fullmatch(r"(\d{1,2})H(\d{2})", h)
    return f"{int(m.group(1)):02d}:{m.group(2)}" if m else h or "a confirmar"


def _kickoff_passed(dj, hora_str, buffer_min: int = 150) -> bool:
    """Retorna True se a hora do jogo + buffer (~duração da partida) já passou.
    Usado para filtrar jogos passados do radar."""
    if not hora_str:
        return False
    m = re.fullmatch(r'(\d{1,2}):(\d{2})', hora_str.strip())
    if not m:
        return False  # hora indefinida — deixa passar
    try:
        h, mi = int(m.group(1)), int(m.group(2))
        kick = datetime.combine(dj, datetime.min.time(), tzinfo=TZ_SP).replace(hour=h, minute=mi)
        return datetime.now(TZ_SP) > kick + timedelta(minutes=buffer_min)
    except Exception:
        return False

def check_agenda():
    today = datetime.now(TZ_SP).date()
    tomorrow = today + timedelta(days=1)
    try:
        with urllib.request.urlopen("https://apiverdao.palmeiras.com.br/wp-json/apiverdao/v1/jogos-mes", timeout=10) as r:
            data = json.load(r)
        hits = [(dj,it) for it in data.get("jogos",[]) if (dj:=_infer_date(it.get("data_jogo",""),today)) in (today,tomorrow)]
        # Remove jogos passados: se for hoje e o kickoff + 150min já passou, descarta
        hits = [(dj,it) for dj,it in hits if not (dj == today and _kickoff_passed(dj, _infer_time(it)))]
        if not hits: return None
        hits.sort(key=lambda x:x[0])
        dj,it = hits[0]
        casa = (it.get("time_casa") or "").strip()
        fora = (it.get("time_visitante") or "").strip()
        adv  = fora if casa.lower()=="palmeiras" else casa
        return {"adversario":adv, "data":dj.strftime("%d/%m/%Y"),
                "hora":_infer_time(it), "hoje":dj==today,
                "competicao":(it.get("campeonato") or "a confirmar").strip(),
                "transmissao":_clean_html(it.get("excecao") or "") or "a confirmar"}
    except Exception as e:
        print(f"[Agenda] API falhou: {e}")
        return _agenda_espn()

def _agenda_espn():
    today = datetime.now(TZ_SP).date()
    tomorrow = today + timedelta(days=1)
    try:
        with urllib.request.urlopen(f"https://site.api.espn.com/apis/site/v2/sports/soccer/all/teams/2029/schedule", timeout=10) as r:
            data = json.load(r)
        for e in data.get("events",[])[:40]:
            dt = datetime.fromisoformat(e["date"].replace("Z","+00:00")).astimezone(TZ_SP)
            if dt.date() not in (today,tomorrow):
                continue
            # Se já é hoje e o kickoff + 150min passou, pula para o próximo
            if dt.date() == today and datetime.now(TZ_SP) > dt + timedelta(minutes=150):
                continue
            return {"adversario":e.get("name","?"), "data":dt.strftime("%d/%m/%Y"),
                    "hora":dt.strftime("%H:%M"), "hoje":dt.date()==today,
                    "competicao":e.get("league",{}).get("name","?"), "transmissao":"a confirmar"}
    except Exception as e:
        print(f"[Agenda] ESPN falhou: {e}")
    return None

def agenda_to_item(a):
    quando = "HOJE" if a["hoje"] else "AMANHÃ"
    title = f"⚽️ JOGO {quando}: Palmeiras x {a['adversario']} — {a['hora']} ({a['competicao']}) | {a['transmissao']}"
    url = "https://palmeiras.com.br/agenda"
    return {"hash":_hash(url+a["data"]), "title":title, "url":url,
            "source":"Agenda Oficial", "published_at":datetime.now(timezone.utc).isoformat(), "score":30}

# ── RSS ────────────────────────────────────────────────────────────────────────
def _rss_image(e):
    """Extrai URL de imagem de uma entrada RSS (media:content, media:thumbnail,
    enclosure ou <img> no summary/description). Retorna None se não encontrar."""
    try:
        for key in ("media_content", "media_thumbnail"):
            items = e.get(key) if isinstance(e, dict) else getattr(e, key, None)
            if items and isinstance(items, list) and items:
                u = items[0].get("url")
                if u:
                    return u
        encs = e.get("enclosures") or []
        for en in encs:
            u  = en.get("href") or en.get("url")
            ty = (en.get("type") or "").lower()
            if u and ("image" in ty or u.lower().endswith((".jpg",".jpeg",".png",".webp",".gif"))):
                return u
        # Fallback: parseia primeiro <img> do summary/description/content.
        html = e.get("summary","") or e.get("description","") or ""
        if not html and e.get("content"):
            try:    html = e["content"][0].get("value","")
            except Exception: pass
        m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', html, flags=re.I)
        if m:
            return m.group(1)
    except Exception:
        pass
    return None


def _og_image(url: str, timeout: int = 6) -> str | None:
    """Baixa o HTML do artigo e extrai og:image / twitter:image (meta tags).
    Usado como último recurso quando o feed RSS não traz imagem inline.
    Limite de 200KB para evitar sugar páginas gigantes."""
    try:
        # Google News usa URLs proxy (news.google.com/rss/articles/…) que redirecionam.
        # urllib segue redirects por padrão.
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml",
        })
        with urllib.request.urlopen(req, timeout=timeout) as r:
            html = r.read(250_000).decode("utf-8", errors="ignore")
        # og:image (Open Graph) — prioritário.
        patterns = (
            r'<meta[^>]+property=["\']og:image(?::secure_url)?["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image(?::secure_url)?["\']',
            r'<meta[^>]+name=["\']twitter:image(?::src)?["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']twitter:image(?::src)?["\']',
        )
        for p in patterns:
            m = re.search(p, html, flags=re.I)
            if m:
                u = m.group(1).strip()
                # HTML entities básicos.
                u = u.replace("&amp;", "&")
                if u.startswith("//"):
                    u = "https:" + u
                if u.startswith("http"):
                    return u
    except Exception:
        pass
    return None


def scrape_rss():
    max_age = NEWS_MAX_AGE_HOURS * 60
    items = []
    for source, url in RSS_FEEDS:
        try:
            for e in feedparser.parse(url).entries[:15]:
                title = e.get("title","").strip()
                link  = e.get("link","").strip()
                if not title or not link: continue
                pub   = _parse_pub(e)
                age   = _age(pub)
                if age > max_age: continue
                s = _score(title)
                if s == 0: continue
                s += 5 if age<30 else (3 if age<60 else 0)
                img = _rss_image(e)
                if not img:
                    # RSS sem imagem — tenta og:image do artigo (apenas para itens
                    # que passaram score+idade, para não inflar latência).
                    img = _og_image(link)
                items.append({"hash":_hash(link),"title":title,"url":link,
                               "source":source,"published_at":pub,"score":s,
                               "image_url": img})
        except Exception as ex:
            print(f"[RSS] {source}: {ex}")
    with_img = sum(1 for it in items if it.get("image_url"))
    print(f"[Scraper] RSS: {len(items)} itens ({with_img} com imagem).")
    return items

# ── TWITTER ────────────────────────────────────────────────────────────────────
async def scrape_twitter():
    """Desativado no servidor. Tweets chegam via pc_twitter_collector.py (IP residencial)."""
    return []

async def _get_tw_api():
    return None

# ── ENTRY POINT ──────────────────────────────
async def run_scraper():
    # Limpa Agenda Oficial velha (jogos passados) do radar
    try:
        from db import mark_past_agendas_as_tweeted
        purged = mark_past_agendas_as_tweeted(NEWS_MAX_AGE_HOURS)
        if purged:
            print(f"[Scraper] Purgado {purged} Agenda(s) Oficial(is) passada(s).")
    except Exception as e:
        print(f"[Scraper] Cleanup falhou: {e}")
    agenda_items = []
    try:
        a = check_agenda()
        if a:
            agenda_items = [agenda_to_item(a)]
            print(f"[Agenda] Jogo {'HOJE' if a['hoje'] else 'AMANHÃ'}: Palmeiras x {a['adversario']}")
    except Exception as e:
        print(f"[Agenda] Erro: {e}")
    rss_items = scrape_rss()
    total = agenda_items + rss_items
    print(f"[Scraper] Total: {len(total)} ({len(agenda_items)} agenda, {len(rss_items)} RSS + tweets do PC no banco).")
    return total

# ── TWITTER ────────────────────────────────────────────────────────────────────
async def scrape_twitter():
    """Desativado no servidor. Tweets chegam via pc_twitter_collector.py (IP residencial)."""
    return []

async def _get_tw_api():
    return None

# ── ENTRY POINT ──────────────────────────────
async def run_scraper():
    # Limpa Agenda Oficial velha (jogos passados) do radar
    try:
        from db import mark_past_agendas_as_tweeted
        purged = mark_past_agendas_as_tweeted(NEWS_MAX_AGE_HOURS)
        if purged:
            print(f"[Scraper] Purgado {purged} Agenda(s) Oficial(is) passada(s).")
    except Exception as e:
        print(f"[Scraper] Cleanup falhou: {e}")
    agenda_items = []
    try:
        a = check_agenda()
        if a:
            agenda_items = [agenda_to_item(a)]
            print(f"[Agenda] Jogo {'HOJE' if a['hoje'] else 'AMANHÃ'}: Palmeiras x {a['adversario']}")
    except Exception as e:
        print(f"[Agenda] Erro: {e}")
    rss_items = scrape_rss()
    total = agenda_items + rss_items
    print(f"[Scraper] Total: {len(total)} ({len(agenda_items)} agenda, {len(rss_items)} RSS + tweets do PC no banco).")
    return total
                    # que passaram score+idade, para não inflar latência).
                    img = _og_image(link)
                items.append({"hash":_hash(link),"title":title,"url":link,
                               "source":source,"published_at":pub,"score":s,
                               "image_url": img})
        except Exception as ex:
            print(f"[RSS] {source}: {ex}")
    with_img = sum(1 for it in items if it.get("image_url"))
    print(f"[Scraper] RSS: {len(items)} itens ({with_img} com imagem).")
    return items

# ── TWITTER ────────────────────────────────────────────────────────────────────
async def scrape_twitter():
    """Desativado no servidor. Tweets chegam via pc_twitter_collector.py (IP residencial)."""
    return []

async def _get_tw_api():
    return None

# ── ENTRY POINT ──────────────────────────────
async def run_scraper():
    # Limpa Agenda Oficial velha (jogos passados) do radar
    try:
        from db import mark_past_agendas_as_tweeted
        purged = mark_past_agendas_as_tweeted(NEWS_MAX_AGE_HOURS)
        if purged:
            print(f"[Scraper] Purgado {purged} Agenda(s) Oficial(is) passada(s).")
    except Exception as e:
        print(f"[Scraper] Cleanup falhou: {e}")
    agenda_items = []
    try:
        a = check_agenda()
        if a:
            agenda_items = [agenda_to_item(a)]
            print(f"[Agenda] Jogo {'HOJE' if a['hoje'] else 'AMANHÃ'}: Palmeiras x {a['adversario']}")
    except Exception as e:
        print(f"[Agenda] Erro: {e}")
    rss_items = scrape_rss()
    total = agenda_items + rss_items
    print(f"[Scraper] Total: {len(total)} ({len(agenda_items)} agenda, {len(rss_items)} RSS + tweets do PC no banco).")
    return total
