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

def check_agenda():
    today = datetime.now(TZ_SP).date()
    tomorrow = today + timedelta(days=1)
    try:
        with urllib.request.urlopen("https://apiverdao.palmeiras.com.br/wp-json/apiverdao/v1/jogos-mes", timeout=10) as r:
            data = json.load(r)
        hits = [(dj,it) for it in data.get("jogos",[]) if (dj:=_infer_date(it.get("data_jogo",""),today)) in (today,tomorrow)]
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
            if dt.date() in (today,tomorrow):
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
                items.append({"hash":_hash(link),"title":title,"url":link,
                               "source":source,"published_at":pub,"score":s})
        except Exception as ex:
            print(f"[RSS] {source}: {ex}")
    print(f"[Scraper] RSS: {len(items)} itens.")
    return items

# ── TWITTER ────────────────────────────────────────────────────────────────────
_tw_api = None

async def _get_tw_api():
    global _tw_api
    if _tw_api: return _tw_api
    api = TwAPI(TWSCRAPE_DB)
    if not await api.pool.get_all():
        print("[twscrape] Adicionando conta scraper...")
        await api.pool.add_account(username=SCRAPER_TWITTER_USER, password=SCRAPER_TWITTER_PASS,
                                   email=SCRAPER_TWITTER_EMAIL, email_password=SCRAPER_TWITTER_EMAIL_PASS)
        await api.pool.login_all()
    _tw_api = api
    return _tw_api

async def scrape_twitter():
    max_age = NEWS_MAX_AGE_HOURS * 60
    items = []
    try:
        api = await _get_tw_api()
    except Exception as e:
        print(f"[twscrape] Init falhou: {e}")
        return []
    for query in ["Palmeiras lang:pt min_faves:50","Palmeiras Libertadores lang:pt","#Palmeiras min_faves:100"]:
        try:
            # Timeout de 30s por query — se rate limit, pula e continua com RSS
            async def _search_with_timeout(q):
                results = []
                async for t in api.search(q, limit=20):
                    results.append(t)
                return results
            import asyncio as _asyncio
            try:
                tweets = await _asyncio.wait_for(_search_with_timeout(query), timeout=30)
            except _asyncio.TimeoutError:
                print(f"[twscrape] Timeout na query '{query}' — pulando.")
                continue
            for t in tweets:
                text = t.rawContent[:250]
                url  = f"https://x.com/{t.user.username}/status/{t.id}"
                pub  = t.date.isoformat() if t.date else datetime.now(timezone.utc).isoformat()
                if _age(pub) > max_age: continue
                s = _score(text)
                if s == 0: continue
                s += (6 if t.likeCount>500 else 3 if t.likeCount>100 else 0)
                s += (4 if t.retweetCount>100 else 2 if t.retweetCount>30 else 0)
                items.append({"hash":_hash(url),"title":text,"url":url,
                               "source":f"Twitter @{t.user.username}",
                               "published_at":pub,"score":s})
        except Exception as e:
            print(f"[twscrape] '{query}': {e}")
    print(f"[Scraper] Twitter: {len(items)} itens.")
    return items

# ── ENTRY POINT ────────────────────────────────────────────────────────────────
async def run_scraper():
    agenda_items = []
    try:
        a = check_agenda()
        if a:
            agenda_items = [agenda_to_item(a)]
            print(f"[Agenda] Jogo {'HOJE' if a['hoje'] else 'AMANHÃ'}: Palmeiras x {a['adversario']}")
    except Exception as e:
        print(f"[Agenda] Erro: {e}")

    rss_items = scrape_rss()
    tw_items  = await scrape_twitter()
    total = agenda_items + rss_items + tw_items
    print(f"[Scraper] Total: {len(total)} ({len(agenda_items)} agenda, {len(rss_items)} RSS, {len(tw_items)} Twitter).")
    return total
