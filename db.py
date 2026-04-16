import sqlite3
import os
from config import DB_PATH


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS news (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            hash         TEXT    UNIQUE,
            title        TEXT,
            url          TEXT,
            source       TEXT,
            published_at TEXT,
            score        INTEGER DEFAULT 0,
            tweeted      INTEGER DEFAULT 0,
            created_at   TEXT    DEFAULT CURRENT_TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS pending_tweets (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            news_ids   TEXT,
            tweet_text TEXT,
            status     TEXT DEFAULT 'pending',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()


def save_news(items: list) -> int:
    """Salva lista de notícias no banco. Retorna quantas eram novas."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    new_count = 0
    for item in items:
        try:
            c.execute("""
                INSERT OR IGNORE INTO news (hash, title, url, source, published_at, score)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (item["hash"], item["title"], item["url"],
                  item["source"], item["published_at"], item["score"]))
            if c.rowcount > 0:
                new_count += 1
        except Exception as e:
            print(f"[DB] Erro ao salvar notícia: {e}")
    conn.commit()
    conn.close()
    return new_count


def get_top_news(limit: int = 8, hours: int = 3) -> list:
    """Retorna as melhores notícias das últimas N horas, por score."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT id, title, url, source, published_at, score
        FROM news
        WHERE datetime(created_at) > datetime('now', ?)
          AND tweeted = 0
        ORDER BY score DESC, created_at DESC
        LIMIT ?
    """, (f"-{hours} hours", limit))
    rows = c.fetchall()
    conn.close()
    return rows


def mark_as_tweeted(news_id: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE news SET tweeted = 1 WHERE id = ?", (news_id,))
    conn.commit()
    conn.close()


def save_pending_tweet(news_ids: list, tweet_text: str) -> int:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT INTO pending_tweets (news_ids, tweet_text)
        VALUES (?, ?)
    """, (",".join(map(str, news_ids)), tweet_text))
    tweet_id = c.lastrowid
    conn.commit()
    conn.close()
    return tweet_id


def get_pending_tweet(tweet_id: int) -> tuple | None:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT id, news_ids, tweet_text
        FROM pending_tweets
        WHERE id = ? AND status = 'pending'
    """, (tweet_id,))
    row = c.fetchone()
    conn.close()
    return row


def update_tweet_status(tweet_id: int, status: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE pending_tweets SET status = ? WHERE id = ?", (status, tweet_id))
    conn.commit()
    conn.close()
