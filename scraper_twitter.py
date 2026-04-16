"""
scraper_twitter.py

Monitora dois tipos de fonte no Twitter/X:
  1. TIMELINES: lista curada de 98 perfis sobre Palmeiras (user_tweets)
     — menos bloqueado de IPs cloud que SearchTimeline
  2. BUSCA POR ENGAJAMENTO: posts virais sobre Palmeiras fora da lista
     — tenta SearchTimeline, mas tem fallback gracioso se bloquear

Perfis organizados por categoria para facilitar manutenção.
"""

import asyncio
from datetime import datetime, timezone
import hashlib

from twscrape import API as TwAPI
from config import (
    TWSCRAPE_DB,
    SCRAPER_TWITTER_USER, SCRAPER_TWITTER_PASS,
    SCRAPER_TWITTER_EMAIL, SCRAPER_TWITTER_EMAIL_PASS,
    NEWS_MAX_AGE_HOURS,
)

# ─────────────────────────────────────────────
# LISTA CURADA DE PERFIS
# ─────────────────────────────────────────────

# Perfis oficiais e da mídia
MEDIA_ACCOUNTS = [
    "Palmeiras",           # conta oficial
    "AllianzParque",       # estádio oficial
    "Palmeiras_FEM",       # futebol feminino
    "geverdao",            # GE setorista
    "lance_palmeiras",     # Lance Palmeiras
    "ESPNBrasil",          # ESPN
    "TNTSportsBR",         # TNT Sports
    "UOLEsporte",          # UOL Esporte
    "palmeirasonline",     # primeiro site do Palmeiras
    "Canal_Palmeiras",     # canal de notícias
    "IPEonline",           # Instituto Palmeiras de Educação
    "midiasep",            # mídia sep
    "jv_midiasep",         # jornalista midiasep
]

# Setoristas e jornalistas
JOURNALIST_ACCOUNTS = [
    "GuiVXavier",          # setorista GE
    "camilac_alves",       # setorista GE
    "reporterfragoso",     # setorista TNT Sports
    "b_ferri",             # setorista GE
    "william_correia",     # podcast Palmeiras
    "veras_midiasep",      # setorista/jornalista
    "Rafa_midiasep",       # jornalista midiasep
    "f_delaurentiis",      # jornalista
    "gabrilamorim",        # apresentador pod Porco
    "pedromarquesfut",     # jornalista
    "sgura",               # jornalista
    "gabrielsantoro",      # jornalista
    "GelmiresCastro",      # jornalista
    "RenanBarreiros",      # jornalista
    "MoisesLima10",        # jornalista
    "williambender",       # jornalista
    "felipef5",            # jornalista
    "kimori",              # jornalista
    "mmurilodias",         # jornalista
    "PepeReale",           # comentarista
    "ClaudioRiicci",       # comentarista
    "DiegoMarada",         # jornalista
    "RBullara",            # jornalista
    "GFalcade21",          # jornalista
    "M_Bortolosso",        # jornalista
    "severogauderio",      # jornalista
    "cesarpessoal",        # jornalista
    "Geguarino",           # jornalista
]

# Jogadores relacionados
PLAYER_ACCOUNTS = [
    "Flaco_Lopez42",       # jogador
    "gustavogomez462",     # jogador
    "gabrielmenino00",     # jogador
    "MuriloPaim",          # jogador
    "facutorresss",        # ex-jogador
]

# Fan accounts / torcida organizada / influencers
FAN_ACCOUNTS = [
    "siamopalestra",
    "Espiaoverde",
    "mundopalmeiras",
    "avantipalmeiras",
    "SEPassessoria",
    "TVPalmeirasFAM",
    "Palmeiras_Press",
    "iGPalmeiras",
    "PauloNobre2011",
    "lanostracasa",
    "clubemondoverde",
    "Ademir_daGuia",
    "magliaverde",
    "verdazzo",
    "mvicca",
    "presuntinhofake",
    "palmeirasHQ",
    "RoubeiaSEP2",
    "GolsdoPalmeiras",
    "ParlaPalestra",
    "memespalmeiras",
    "HistoriadorSEP",
    "BoasdoPalmeiras",
    "SERGIOSEPSEP2",
    "Palmeiras_VK",
    "BasePalmeiras",
    "armada1914",
    "palestragaluppo",
    "AquiEhParmera",
    "Tifosi14sep",
    "verdaoinfo1",
    "SEPalmeirasBR",
    "guigpereira",
    "Infos_palestra",
    "deprepalmeiras",
    "vaiparmera",
    "Amici1914",
    "weS2_",
    "JApparec",
    "parmeramilgrau",
    "leilapereiralp",
    "ocupa_palestra",
    "AnyPalmeiras",
    "PalmeirasTour",
    "onossopalestra",
    "Massimo_divino",
    "palmeirastuff",
    "torcidamv83",
    "twitpalmeiras",
    "AnaliseVerdao",
    "JogueinaSEP",
    "OfficialCorredor",
    "taticapalmeiras",
    "_AcademiaStore",
]

# Lista completa para monitorar
ALL_ACCOUNTS = MEDIA_ACCOUNTS + JOURNALIST_ACCOUNTS + PLAYER_ACCOUNTS + FAN_ACCOUNTS

# ─────────────────────────────────────────────
# KEYWORDS PARA SCORING
# ─────────────────────────────────────────────
KW_PALMEIRAS = [
    "palmeiras", "verdão", "alviverde", "abel", "veiga",
    "estêvão", "weverton", "libertadores", "paulistão",
    "brasileiro", "allianz", "parque", "porco", "sep",
    "palestra", "palestrina", "1914",
]

def _score(text: str) -> int:
    t = text.lower()
    return sum(8 for k in KW_PALMEIRAS if k in t)

def _hash(u): return hashlib.md5(u.encode()).hexdigest()

def _age(iso):
    try:
        pub = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if not pub.tzinfo: pub = pub.replace(tzinfo=timezone.utc)
        return int((datetime.now(timezone.utc) - pub).total_seconds() / 60)
    except: return 9999

def _get_image(tweet) -> str | None:
    try:
        if hasattr(tweet, "media") and tweet.media:
            for m in tweet.media:
                if hasattr(m, "url") and m.url:
                    return m.url
    except: pass
    return None


# ─────────────────────────────────────────────
# SINGLETON DA API
# ─────────────────────────────────────────────
_tw_api = None
_user_id_cache: dict = {}

async def _get_api():
    global _tw_api
    if _tw_api: return _tw_api
    api = TwAPI(TWSCRAPE_DB)
    accounts = await api.pool.get_all()
    if not accounts:
        print("[Twitter] Nenhuma conta configurada.")
        return None
    active = [a for a in accounts if a.active]
    if not active:
        print(f"[Twitter] {len(accounts)} conta(s) registrada(s) mas nenhuma ativa.")
        return None
    print(f"[Twitter] {len(active)} conta(s) ativa(s).")
    _tw_api = api
    return _tw_api

async def _get_user_id(api, username: str) -> int | None:
    if username in _user_id_cache:
        return _user_id_cache[username]
    try:
        user = await asyncio.wait_for(api.user_by_login(username), timeout=10)
        if user:
            _user_id_cache[username] = user.id
            return user.id
    except Exception as e:
        print(f"[Twitter] user_by_login @{username}: {e}")
    return None


# ─────────────────────────────────────────────
# 1. TIMELINES (lista curada)
# ─────────────────────────────────────────────
async def _scrape_timeline(api, username: str, max_age: int) -> list:
    items = []
    try:
        user_id = await _get_user_id(api, username)
        if not user_id:
            return []
        async for tweet in api.user_tweets(user_id, limit=5):
            text = tweet.rawContent[:300]
            url  = f"https://x.com/{username}/status/{tweet.id}"
            pub  = tweet.date.isoformat() if tweet.date else datetime.now(timezone.utc).isoformat()
            if _age(pub) > max_age:
                continue
            score = _score(text)
            if score == 0:
                # Contas 100% palmeiras: aceita qualquer post recente
                if username.lower() in [a.lower() for a in MEDIA_ACCOUNTS + PLAYER_ACCOUNTS]:
                    score = 8
                else:
                    continue
            # Bônus por engajamento
            if tweet.likeCount    > 1000: score += 8
            elif tweet.likeCount  > 300:  score += 5
            elif tweet.likeCount  > 100:  score += 3
            if tweet.retweetCount > 200:  score += 6
            elif tweet.retweetCount > 50: score += 3
            items.append({
                "hash":         _hash(url),
                "title":        text,
                "url":          url,
                "source":       f"Twitter @{username}",
                "published_at": pub,
                "score":        score,
                "image_url":    _get_image(tweet),
            })
    except asyncio.TimeoutError:
        print(f"[Twitter] Timeout @{username}")
    except Exception as e:
        print(f"[Twitter] Erro @{username}: {type(e).__name__}")
    return items


async def scrape_timelines(max_age: int = None) -> list:
    if max_age is None:
        max_age = NEWS_MAX_AGE_HOURS * 60
    api = await _get_api()
    if not api:
        return []

    all_items = []
    # Processa em lotes de 10 para não sobrecarregar
    batch_size = 10
    for i in range(0, len(ALL_ACCOUNTS), batch_size):
        batch = ALL_ACCOUNTS[i:i+batch_size]
        tasks = [_scrape_timeline(api, username, max_age) for username in batch]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, list):
                all_items.extend(result)
        await asyncio.sleep(1)  # pausa entre lotes

    print(f"[Twitter] Timelines: {len(all_items)} tweets relevantes de {len(ALL_ACCOUNTS)} perfis.")
    return all_items


# ─────────────────────────────────────────────
# 2. BUSCA POR ENGAJAMENTO (posts virais fora da lista)
# ─────────────────────────────────────────────
async def scrape_engagement_search(max_age: int = None) -> list:
    """
    Tenta SearchTimeline para capturar posts virais sobre Palmeiras
    que não são de perfis monitorados.
    Tem timeout de 20s — se bloquear, retorna lista vazia sem travar.
    """
    if max_age is None:
        max_age = NEWS_MAX_AGE_HOURS * 60
    api = await _get_api()
    if not api:
        return []

    items = []
    # Queries focadas em alto engajamento para capturar opinião da torcida
    queries = [
        "Palmeiras min_faves:200 lang:pt",
        "Verdão min_faves:200 lang:pt",
        "#Palmeiras min_faves:100",
    ]

    for query in queries:
        try:
            count = 0
            async for tweet in api.search(query, limit=15):
                text = tweet.rawContent[:300]
                url  = f"https://x.com/{tweet.user.username}/status/{tweet.id}"
                pub  = tweet.date.isoformat() if tweet.date else datetime.now(timezone.utc).isoformat()
                if _age(pub) > max_age:
                    continue
                score = _score(text)
                if score == 0:
                    continue
                # Bônus maior por engajamento (esses são posts virais)
                if tweet.likeCount    > 5000: score += 15
                elif tweet.likeCount  > 1000: score += 10
                elif tweet.likeCount  > 200:  score += 6
                if tweet.retweetCount > 500:  score += 10
                elif tweet.retweetCount > 100: score += 5
                items.append({
                    "hash":         _hash(url),
                    "title":        text,
                    "url":          url,
                    "source":       f"Twitter viral @{tweet.user.username}",
                    "published_at": pub,
                    "score":        score,
                    "image_url":    _get_image(tweet),
                })
                count += 1
            if count:
                print(f"[Twitter Search] '{query[:40]}': {count} tweets virais")
        except asyncio.TimeoutError:
            print(f"[Twitter Search] Timeout — IP bloqueado, pulando busca viral.")
            break
        except Exception as e:
            print(f"[Twitter Search] '{query[:40]}': {type(e).__name__} — pulando.")

    print(f"[Twitter] Busca viral: {len(items)} tweets.")
    return items


# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────
async def scrape_twitter_all() -> list:
    """
    Combina timelines (lista curada) + busca viral (engajamento).
    Ambas têm timeout e fallback — nunca travam o ciclo principal.
    """
    max_age = NEWS_MAX_AGE_HOURS * 60

    timeline_items  = []
    engagement_items = []

    try:
        timeline_items = await asyncio.wait_for(
            scrape_timelines(max_age), timeout=90
        )
    except asyncio.TimeoutError:
        print("[Twitter] Timeout geral nas timelines.")
    except Exception as e:
        print(f"[Twitter] Erro nas timelines: {e}")

    try:
        engagement_items = await asyncio.wait_for(
            scrape_engagement_search(max_age), timeout=30
        )
    except asyncio.TimeoutError:
        print("[Twitter] Timeout na busca viral — seguindo só com timelines.")
    except Exception as e:
        print(f"[Twitter] Erro na busca viral: {e}")

    total = timeline_items + engagement_items
    # Remove duplicatas por hash
    seen = set()
    unique = []
    for item in total:
        if item["hash"] not in seen:
            seen.add(item["hash"])
            unique.append(item)

    print(f"[Twitter] Total: {len(unique)} tweets únicos ({len(timeline_items)} timelines + {len(engagement_items)} virais).")
    return unique
