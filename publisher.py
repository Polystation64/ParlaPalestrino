import tweepy
from config import (
    TWITTER_API_KEY, TWITTER_API_SECRET,
    TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_SECRET,
    TWITTER_HANDLE,
)


def _client() -> tweepy.Client:
    return tweepy.Client(
        consumer_key=TWITTER_API_KEY,
        consumer_secret=TWITTER_API_SECRET,
        access_token=TWITTER_ACCESS_TOKEN,
        access_token_secret=TWITTER_ACCESS_SECRET,
    )


def post_tweet(text: str) -> dict:
    """
    Posta um tweet e retorna dict com success, tweet_id e url.
    """
    try:
        client   = _client()
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
