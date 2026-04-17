"""
pc_twitter_collector.py — usa twscrape (mesmo do servidor)

Roda NO SEU PC (IP residencial).
Busca tweets sobre Palmeiras e envia para o servidor.

Configuração:
  1. Preenche as variáveis no bloco CONFIG
  2. Roda UMA VEZ para configurar: python pc_twitter_collector.py --setup
  3. Depois roda normalmente: python pc_twitter_collector.py
  4. Agenda no Agendador de Tarefas do Windows a cada 30min
"""

import asyncio
import json
import hashlib
import sys
import httpx
from datetime import datetime, timezone
from twscrape import API

# ─────────────────────────────────────────────
# CONFIG — preenche aqui
# ─────────────────────────────────────────────
SERVER_URL   = "http://54.233.174.77:8765/tweets"
BOT_TOKEN    = "parla2026verde"

# Cookies da sua conta principal do Twitter
# Exporta pelo Cookie-Editor no Chrome em x.com
AUTH_TOKEN = "COLE_SEU_AUTH_TOKEN_AQUI"
CT0        = "COLE_SEU_CT0_AQUI"

# Usuário do Twitter (sem @)
TWITTER_USERNAME = "COLE_SEU_USUARIO_AQUI"
# ─────────────────────────────────────────────

DB_PATH = "pc_accounts.db"

SEARCH_QUERIES = [
    ("Palmeiras min_faves:100 lang:pt",  15),
    ("#Palmeiras min_faves:50",          15),
    ("Verdão min_faves:100 lang:pt",     15),
    ("Palmeiras Libertadores lang:pt",   10),
    ("Abel Ferreira Palmeiras lang:pt",  10),
    ("Estêvão Palmeiras lang:pt",        10),
    ("Palmeiras escalação lang:pt",      10),
    ("Palmeiras contratação lang:pt",    10),
]

KW_PALMEIRAS = [
    "palmeiras", "verdão", "alviverde", "abel", "veiga",
    "estêvão", "weverton", "libertadores", "paulistão",
    "brasileiro", "allianz", "porco", "sep", "palestra",
]

def _score(text: str) -> int:
    t = text.lower()
    return max(sum(8 for k in KW_PALMEIRAS if k in t), 8)

def _hash(u): return hashlib.md5(u.encode()).hexdigest()

def _get_image(tweet) -> str | None:
    try:
        if hasattr(tweet, "media") and tweet.media:
            for m in tweet.media:
                if hasattr(m, "url") and m.url:
                    return m.url
    except: pass
    return None


async def setup():
    """Configura a conta twscrape com cookies. Roda só uma vez."""
    api = API(DB_PATH)
    cookies_str = f"auth_token={AUTH_TOKEN}; ct0={CT0}"
    await api.pool.add_account(
        username=TWITTER_USERNAME,
        password="n/a",
        email="n/a",
        email_password="n/a",
        cookies=cookies_str,
    )
    accounts = await api.pool.get_all()
    for a in accounts:
        print(f"Conta: @{a.username} | ativa: {a.active}")
    print("Setup concluído! Agora rode sem --setup.")


async def collect() -> list:
    print(f"[PC] Iniciando — {datetime.now().strftime('%d/%m %H:%M:%S')}")

    api      = API(DB_PATH)
    accounts = await api.pool.get_all()
    active   = [a for a in accounts if a.active]

    if not active:
        print("[PC] Nenhuma conta ativa. Rode com --setup primeiro.")
        return []

    print(f"[PC] Conta: @{active[0].username}")

    all_items = []
    seen_ids  = set()

    for query, limit in SEARCH_QUERIES:
        try:
            print(f"[PC] Buscando: {query[:50]}...")
            count = 0
            async for tweet in api.search(query, limit=limit):
                tid = str(tweet.id)
                if tid in seen_ids:
                    continue
                seen_ids.add(tid)

                text = tweet.rawContent[:300]
                url  = f"https://x.com/{tweet.user.username}/status/{tweet.id}"
                pub  = tweet.date.isoformat() if tweet.date else datetime.now(timezone.utc).isoformat()

                score = _score(text)
                likes = getattr(tweet, "likeCount",    0) or 0
                rts   = getattr(tweet, "retweetCount", 0) or 0

                if likes  > 5000: score += 15
                elif likes > 1000: score += 10
                elif likes > 200:  score += 6
                elif likes > 50:   score += 3
                if rts    > 500:   score += 10
                elif rts  > 100:   score += 5
                elif rts  > 20:    score += 2

                all_items.append({
                    "text":         text,
                    "url":          url,
                    "source":       f"Twitter @{tweet.user.username} (PC)",
                    "published_at": pub,
                    "score":        score,
                    "image_url":    _get_image(tweet),
                })
                count += 1

            print(f"  → {count} tweets")
            await asyncio.sleep(2)

        except Exception as e:
            print(f"  → Erro: {type(e).__name__}: {e}")
            await asyncio.sleep(3)

    print(f"[PC] Total: {len(all_items)} tweets únicos.")
    return all_items


def send_to_server(tweets: list):
    if not tweets:
        print("[PC] Nenhum tweet para enviar.")
        return

    try:
        resp = httpx.post(
            SERVER_URL,
            json=tweets,
            headers={"X-Bot-Token": BOT_TOKEN},
            timeout=30,
        )
        if resp.status_code == 200:
            data = resp.json()
            print(f"[PC] Servidor: {data.get('total',0)} recebidos, {data.get('saved',0)} novos.")
        else:
            print(f"[PC] Erro no servidor: {resp.status_code}")
    except Exception as e:
        print(f"[PC] Falha ao enviar: {e}")


async def main():
    if "--setup" in sys.argv:
        await setup()
        return
    tweets = await collect()
    send_to_server(tweets)
    print(f"[PC] Concluído — {datetime.now().strftime('%H:%M:%S')}")


if __name__ == "__main__":
    asyncio.run(main())
