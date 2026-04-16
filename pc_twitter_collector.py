"""
pc_twitter_collector.py

Roda NO SEU PC (IP residencial).
Busca tweets sobre Palmeiras no Twitter/X e envia para o servidor.

Configuração:
  1. Preenche as variáveis no bloco CONFIG abaixo
  2. Exporta cookies da sua conta do Twitter (Cookie-Editor no Chrome)
  3. Roda: python pc_twitter_collector.py
  4. Agenda no Agendador de Tarefas do Windows para rodar a cada 30min

Dependências (instala uma vez):
  pip install twikit httpx
"""

import asyncio
import json
import hashlib
import httpx
from datetime import datetime, timezone
from twikit import Client

# ─────────────────────────────────────────────
# CONFIG — preenche aqui
# ─────────────────────────────────────────────
SERVER_URL   = "http://54.233.174.77:8765/tweets"
BOT_TOKEN    = "COLE_O_RECEIVER_TOKEN_AQUI"   # mesmo valor do .env no servidor

# Cookies da sua conta do Twitter (exportados pelo Cookie-Editor)
# Só precisa do auth_token e ct0
TWITTER_COOKIES = {
    "auth_token": "COLE_SEU_AUTH_TOKEN_AQUI",
    "ct0":        "COLE_SEU_CT0_AQUI",
}

TWITTER_USERNAME = "alexandre"  # seu username no Twitter (sem @)
# ─────────────────────────────────────────────

# Queries de busca — mistura notícias + opinião da torcida
SEARCH_QUERIES = [
    ("Palmeiras min_faves:100 lang:pt",     "viral"),
    ("#Palmeiras min_faves:50",             "hashtag"),
    ("Verdão min_faves:100 lang:pt",        "viral"),
    ("Palmeiras Libertadores lang:pt",      "libertadores"),
    ("Abel Ferreira Palmeiras lang:pt",     "abel"),
    ("Estêvão Palmeiras lang:pt",           "estevao"),
    ("Palmeiras escalação lang:pt",         "escalacao"),
    ("Palmeiras contratação lang:pt",       "mercado"),
]

KW_PALMEIRAS = [
    "palmeiras", "verdão", "alviverde", "abel", "veiga",
    "estêvão", "weverton", "libertadores", "paulistão",
    "brasileiro", "allianz", "porco", "sep", "palestra",
]

def _score(text: str, query_type: str) -> int:
    t = text.lower()
    s = sum(8 for k in KW_PALMEIRAS if k in t)
    # Bônus por tipo de query
    if query_type in ("viral", "hashtag"):
        s += 5
    return max(s, 8)  # mínimo 8 (já passou pelo filtro da query)

def _hash(u): return hashlib.md5(u.encode()).hexdigest()

def _get_image(tweet) -> str | None:
    try:
        if hasattr(tweet, "media") and tweet.media:
            for m in tweet.media:
                url = getattr(m, "media_url_https", None) or getattr(m, "url", None)
                if url:
                    return url
    except: pass
    return None


async def collect_tweets() -> list:
    print(f"[PC Collector] Iniciando coleta — {datetime.now().strftime('%H:%M:%S')}")

    client = Client("pt-BR")

    # Carrega cookies (sem fazer login, usa sessão existente)
    try:
        client.set_cookies(TWITTER_COOKIES)
        print("[PC Collector] Cookies carregados.")
    except Exception as e:
        print(f"[PC Collector] Erro ao carregar cookies: {e}")
        return []

    all_tweets = []
    seen_ids   = set()

    for query, qtype in SEARCH_QUERIES:
        try:
            print(f"[PC Collector] Buscando: {query[:50]}...")
            results = await client.search_tweet(query, product="Latest", count=20)

            count = 0
            for tweet in results:
                tid = str(tweet.id)
                if tid in seen_ids:
                    continue
                seen_ids.add(tid)

                text     = tweet.full_text or tweet.text or ""
                username = tweet.user.screen_name if tweet.user else "unknown"
                url      = f"https://x.com/{username}/status/{tid}"
                pub      = tweet.created_at_datetime.isoformat() if tweet.created_at_datetime else datetime.now(timezone.utc).isoformat()

                score = _score(text, qtype)

                # Bônus por engajamento real
                likes = getattr(tweet, "favorite_count", 0) or 0
                rts   = getattr(tweet, "retweet_count",  0) or 0
                if likes  > 5000: score += 15
                elif likes > 1000: score += 10
                elif likes > 200:  score += 6
                elif likes > 50:   score += 3
                if rts    > 500:   score += 10
                elif rts  > 100:   score += 5
                elif rts  > 20:    score += 2

                all_tweets.append({
                    "text":         text[:300],
                    "url":          url,
                    "source":       f"Twitter @{username} (PC)",
                    "published_at": pub,
                    "score":        score,
                    "image_url":    _get_image(tweet),
                    "likes":        likes,
                    "retweets":     rts,
                })
                count += 1

            print(f"  → {count} tweets coletados")
            await asyncio.sleep(3)  # pausa entre queries

        except Exception as e:
            print(f"[PC Collector] Erro na query '{query[:40]}': {e}")
            await asyncio.sleep(5)

    print(f"[PC Collector] Total: {len(all_tweets)} tweets únicos.")
    return all_tweets


def send_to_server(tweets: list) -> bool:
    if not tweets:
        print("[PC Collector] Nenhum tweet para enviar.")
        return True

    try:
        resp = httpx.post(
            SERVER_URL,
            json=tweets,
            headers={"X-Bot-Token": BOT_TOKEN},
            timeout=30,
        )
        if resp.status_code == 200:
            data = resp.json()
            print(f"[PC Collector] Enviados: {data.get('total',0)} tweets, {data.get('saved',0)} novos no banco.")
            return True
        else:
            print(f"[PC Collector] Servidor retornou: {resp.status_code} — {resp.text[:200]}")
            return False
    except Exception as e:
        print(f"[PC Collector] Erro ao enviar para o servidor: {e}")
        return False


async def main():
    tweets = await collect_tweets()
    send_to_server(tweets)
    print(f"[PC Collector] Concluído — {datetime.now().strftime('%H:%M:%S')}")


if __name__ == "__main__":
    asyncio.run(main())
