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
            image_url    TEXT,
            tweeted      INTEGER DEFAULT 0,
            created_at   TEXT    DEFAULT CURRENT_TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS pending_tweets (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            news_ids   TEXT,
            tweet_text TEXT,
            image_url  TEXT,
            status     TEXT DEFAULT 'pending',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Migrações idempotentes para bancos antigos (adiciona colunas se faltarem).
    for table, col, ctype in (
        ("news",            "image_url", "TEXT"),
        ("pending_tweets",  "image_url", "TEXT"),
    ):
        try:
            c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ctype}")
        except sqlite3.OperationalError:
            pass  # coluna já existe

    conn.commit()
    conn.close()


def save_news(items: list) -> int:
    """Salva lista de notícias no banco. Retorna quantas eram novas.
    Para 'Agenda Oficial' atualiza título/score/published_at/image_url a cada ciclo
    para manter o card 'o próximo jogo' sempre fresco enquanto ainda é relevante."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    new_count = 0
    for item in items:
        try:
            c.execute("""
                INSERT INTO news (hash, title, url, source, published_at, score, image_url)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(hash) DO UPDATE SET
                    title        = excluded.title,
                    published_at = excluded.published_at,
                    score        = excluded.score,
                    image_url    = COALESCE(excluded.image_url, news.image_url)
                WHERE news.source = 'Agenda Oficial'
            """, (item["hash"], item["title"], item["url"], item["source"],
                  item["published_at"], item["score"], item.get("image_url")))
            if c.rowcount > 0:
                new_count += 1
        except Exception as e:
            print(f"[DB] Erro ao salvar notícia: {e}")
    conn.commit()
    conn.close()
    return new_count


def get_top_news(limit: int = 8, hours: int | None = None) -> list:
    """Retorna as melhores notícias dentro da janela de tempo, por score.
    - Filtra SEMPRE por published_at (hora real da notícia), nunca created_at.
    - Aplica o MESMO filtro de tempo a todos os items (inclusive Agenda Oficial).
      Para Agenda, o scraper mantém published_at fresco enquanto o jogo ainda é
      relevante; depois que check_agenda para de renovar, a linha envelhece e
      cai naturalmente da janela. Sem esse filtro, jogos passados ficam eternos.
    """
    from config import NEWS_MAX_AGE_HOURS
    if hours is None:
        hours = NEWS_MAX_AGE_HOURS
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT id, title, url, source, published_at, score,
               COALESCE(image_url, '') AS image_url
        FROM news
        WHERE tweeted = 0
          AND datetime(published_at) > datetime('now', ?)
        ORDER BY score DESC, published_at DESC
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


def mark_past_agendas_as_tweeted(hours: int = 6) -> int:
    """Marca itens 'Agenda Oficial' cujo published_at já passou do limite como
    tweeted=1 para limpá-los do radar definitivamente. Chamado pelo scraper."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        UPDATE news SET tweeted = 1
        WHERE source = 'Agenda Oficial'
          AND tweeted = 0
          AND datetime(published_at) <= datetime('now', ?)
    """, (f"-{hours} hours",))
    n = c.rowcount
    conn.commit()
    conn.close()
    return n


def save_pending_tweet(news_ids: list, tweet_text: str, image_url: str | None = None) -> int:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT INTO pending_tweets (news_ids, tweet_text, image_url)
        VALUES (?, ?, ?)
    """, (",".join(map(str, news_ids)), tweet_text, image_url))
    tweet_id = c.lastrowid
    conn.commit()
    conn.close()
    return tweet_id


def get_pending_tweet(tweet_id: int) -> tuple | None:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT id, news_ids, tweet_text, image_url
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
