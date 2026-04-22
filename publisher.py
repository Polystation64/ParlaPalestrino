import os
import tempfile
import urllib.request

import tweepy

from config import (
    TWITTER_API_KEY, TWITTER_API_SECRET,
    TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_SECRET,
    TWITTER_HANDLE,
)


def _client() -> tweepy.Client:
    """Twitter API v2 — para criar tweets."""
    return tweepy.Client(
        consumer_key=TWITTER_API_KEY,
        consumer_secret=TWITTER_API_SECRET,
        access_token=TWITTER_ACCESS_TOKEN,
        access_token_secret=TWITTER_ACCESS_SECRET,
    )


def _v1_api() -> tweepy.API:
    """Twitter API v1.1 — necessária para upload de mídia (media_upload)."""
    auth = tweepy.OAuth1UserHandler(
        TWITTER_API_KEY, TWITTER_API_SECRET,
        TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_SECRET,
    )
    return tweepy.API(auth)


def _download_image(url: str) -> str | None:
    """Baixa imagem para arquivo temporário. Retorna path ou None em falha."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = r.read()
        # Sniff extensão pelo URL (ignora querystring).
        lower = url.lower().split("?")[0]
        ext = ".jpg"
        for e in (".png", ".jpeg", ".jpg", ".gif", ".webp"):
            if lower.endswith(e):
                ext = ".jpg" if e == ".jpeg" else e
                break
        fd, path = tempfile.mkstemp(suffix=ext, prefix="pp_img_")
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        return path
    except Exception as e:
        print(f"[Publisher] Falha ao baixar imagem {url}: {e}")
        return None


def post_tweet(text: str, image_url: str | None = None) -> dict:
    """
    Posta um tweet (opcionalmente com imagem) e retorna dict com success, tweet_id e url.
    Se a imagem falhar (download ou upload), cai para tweet só-texto em vez de abortar.
    """
    img_path = None
    try:
        client = _client()
        media_ids = None

        if image_url:
            img_path = _download_image(image_url)
            if img_path:
                try:
                    api = _v1_api()
                    media = api.media_upload(filename=img_path)
                    media_ids = [media.media_id]
                except Exception as e:
                    print(f"[Publisher] Upload de mídia falhou, tweetando sem imagem: {e}")
                    media_ids = None

        if media_ids:
            response = client.create_tweet(text=text, media_ids=media_ids)
        else:
            response = client.create_tweet(text=text)

        tweet_id = response.data["id"]
        return {
            "success":  True,
            "tweet_id": tweet_id,
            "url":      f"https://twitter.com/{TWITTER_HANDLE}/status/{tweet_id}",
        }
    except tweepy.TweepyException as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": f"Erro inesperado: {e}"}
    finally:
        if img_path:
            try:
                os.remove(img_path)
            except Exception:
                pass
