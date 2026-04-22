"""
pc_twitter_collector.py — versão final com Scweet 5.3

Roda NO SEU PC (IP residencial).
Busca tweets sobre Palmeiras e envia para o servidor.

Instala: pip install scweet httpx
Preenche AUTH_TOKEN, CT0 e TWITTER_USERNAME abaixo.
Agenda no Agendador de Tarefas do Windows a cada 30min.
"""

import os
import json
import hashlib
import httpx
from datetime import datetime, timezone, timedelta

# ─────────────────────────────────────────────
# CONFIG — preenche aqui
# ─────────────────────────────────────────────
SERVER_URL       = "http://54.233.174.77:8765/tweets"
BOT_TOKEN        = "parla2026verde"
AUTH_TOKEN       = "00bc17479d9b5a89f120c4a6fdd44b9852be35af"
CT0              = "514f38a6d9e3bae7c54da6d3d2733be26f902864d94967514b4b307331e70ea19ca345a1f63e5ba7788dd13bd136c772c2c6bcfc5037eb29c2a3fc16bdf43d9c5db7f65ae367645b77aea9f22990a2a9"
TWITTER_USERNAME = "oscardashopee"
STATE_DB         = "scweet_state.db"   # apagado a cada run para resetar limites
# ─────────────────────────────────────────────

# 4 queries por ciclo — equilibrio entre cobertura e limite da conta
SEARCH_QUERIES = [
    "#Palmeiras min_faves:50",
    "Palmeiras min_faves:100 lang:pt",
    "Verdão OR Alviverde min_faves:100 lang:pt",
    "Palmeiras Libertadores OR escalação OR contratação lang:pt",
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


def collect_tweets() -> list:
    print(f"[PC] Iniciando — {datetime.now().strftime('%d/%m %H:%M:%S')}")

    # Apaga o estado anterior para resetar o contador diário do Scweet
    if os.path.exists(STATE_DB):
        os.remove(STATE_DB)
        print("[PC] Estado resetado.")

    try:
        from Scweet import Scweet
    except ImportError:
        print("[PC] Scweet não instalado. Rode: pip install scweet")
        return []

    try:
        s = Scweet(auth_token=AUTH_TOKEN)
        print(f"[PC] Autenticado como @{TWITTER_USERNAME}")
    except Exception as e:
        print(f"[PC] Erro de autenticação: {e}")
        return []

    # Busca tweets das últimas 3 horas
    since = (datetime.now() - timedelta(hours=3)).strftime("%Y-%m-%d")

    all_items = []
    seen_ids  = set()

    for query in SEARCH_QUERIES:
        try:
            print(f"[PC] Buscando: {query[:60]}...")
            tweets = s.search(query, since=since, limit=25, save=False)

            if not tweets:
                print("  → Sem resultados")
                continue

            count = 0
            for tweet in tweets:
                # Scweet 5.3 retorna dicts (via model_dump) com estrutura aninhada:
                #   { tweet_id, user:{screen_name,name}, timestamp, text, embedded_text,
                #     likes, retweets, comments, media:{image_links:[...]}, tweet_url, raw:{...} }
                tid = str(tweet.get("tweet_id") or tweet.get("id") or "")
                if not tid or tid in seen_ids:
                    continue
                seen_ids.add(tid)

                text = str(
                    tweet.get("text")
                    or tweet.get("embedded_text")
                    or tweet.get("full_text")
                    or ""
                )[:300]

                # user é sempre um dict aninhado no Scweet 5.3.
                user_obj = tweet.get("user") or {}
                if isinstance(user_obj, dict):
                    username = user_obj.get("screen_name") or user_obj.get("name") or "palmeiras_fan"
                else:
                    username = str(user_obj) or "palmeiras_fan"
                username = str(username).strip().lstrip("@").replace(" ", "")[:50] or "palmeiras_fan"

                url = tweet.get("tweet_url") or f"https://x.com/{username}/status/{tid}"
                raw_pub = tweet.get("timestamp") or tweet.get("created_at")
                pub = None
                if raw_pub:
                    try:
                        # Se for int/float ou string de dígitos (timestamp Unix)
                        if isinstance(raw_pub, (int, float)) or (isinstance(raw_pub, str) and raw_pub.isdigit()):
                            pub = datetime.fromtimestamp(float(raw_pub), timezone.utc).isoformat()
                        elif isinstance(raw_pub, str):
                            # Tenta parsear formato nativo do Twitter (ex: "Mon Apr 21 16:16:48 +0000 2026")
                            if len(raw_pub.split()) == 6 and "+0000" in raw_pub:
                                pub = datetime.strptime(raw_pub, "%a %b %d %H:%M:%S %z %Y").astimezone(timezone.utc).isoformat()
                            elif raw_pub.endswith("Z") or "T" in raw_pub:
                                pub = raw_pub  # ISO format já compatível com sqlite
                    except Exception as e:
                        print(f"Erro parseando data {raw_pub}: {e}")
                
                if not pub:
                    pub = datetime.now(timezone.utc).isoformat()

                # Campos novos do Scweet 5.3: `likes` e `retweets` (sem sufixo _count).
                likes = int(tweet.get("likes") or tweet.get("likes_count") or tweet.get("favorite_count") or 0)
                rts   = int(tweet.get("retweets") or tweet.get("retweet_count") or 0)

                score = _score(text)
                if likes  > 5000: score += 15
                elif likes > 1000: score += 10
                elif likes > 200:  score += 6
                elif likes > 50:   score += 3
                if rts    > 500:   score += 10
                elif rts  > 100:   score += 5
                elif rts  > 20:    score += 2

                # Imagem: tweet["media"]["image_links"][0] em Scweet 5.3.
                image_url = None
                media_obj = tweet.get("media") or {}
                if isinstance(media_obj, dict):
                    imgs = media_obj.get("image_links") or []
                    if imgs:
                        image_url = imgs[0]
                # Fallback: alguns exports antigos expõem direto em image_links.
                if not image_url:
                    imgs = tweet.get("image_links") or []
                    if imgs and isinstance(imgs, list):
                        image_url = imgs[0]

                all_items.append({
                    "text":         text,
                    "url":          url,
                    "source":       f"Twitter @{username} (PC)",
                    "published_at": pub,
                    "score":        score,
                    "image_url":    image_url,
                })
                count += 1

            print(f"  → {count} tweets")

        except Exception as e:
            print(f"  → Erro: {type(e).__name__}: {e}")

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
            print(f"[PC] ✅ Servidor: {data.get('total',0)} recebidos, {data.get('saved',0)} novos.")
        else:
            print(f"[PC] ❌ Servidor retornou: {resp.status_code}")
    except Exception as e:
        print(f"[PC] ❌ Falha ao enviar: {e}")


if __name__ == "__main__":
    tweets = collect_tweets()
    send_to_server(tweets)
    print(f"[PC] Concluído — {datetime.now().strftime('%H:%M:%S')}")
