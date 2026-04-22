import os
from dotenv import load_dotenv

load_dotenv()

# Telegram
TELEGRAM_BOT_TOKEN  = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID    = int(os.getenv("TELEGRAM_CHAT_ID", "0"))

# Twitter - conta principal para POSTAR
TWITTER_API_KEY        = os.getenv("TWITTER_API_KEY")
TWITTER_API_SECRET     = os.getenv("TWITTER_API_SECRET")
TWITTER_ACCESS_TOKEN   = os.getenv("TWITTER_ACCESS_TOKEN")
TWITTER_ACCESS_SECRET  = os.getenv("TWITTER_ACCESS_SECRET")
TWITTER_HANDLE         = "ParlaPalestrino"

# Twitter - conta FANTASMA para buscar via twscrape
SCRAPER_TWITTER_USER       = os.getenv("SCRAPER_TWITTER_USER")
SCRAPER_TWITTER_PASS       = os.getenv("SCRAPER_TWITTER_PASS")
SCRAPER_TWITTER_EMAIL      = os.getenv("SCRAPER_TWITTER_EMAIL")
SCRAPER_TWITTER_EMAIL_PASS = os.getenv("SCRAPER_TWITTER_EMAIL_PASS")

# Modelos de IA (usados em ordem de fallback pelo generator.py)
GROQ_API_KEY       = os.getenv("GROQ_API_KEY")
GROQ_MODEL         = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL   = os.getenv("OPENROUTER_MODEL", "google/gemma-4-31b-it:free")

OLLAMA_BASE_URL    = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
OLLAMA_API_KEY     = os.getenv("OLLAMA_API_KEY", "ollama")
OLLAMA_MODEL       = os.getenv("OLLAMA_MODEL", "glm-4")

OPENAI_API_KEY     = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL       = os.getenv("OPENAI_MODEL", "gpt-4o")

# Configurações gerais
SCRAPE_INTERVAL_MINUTES = int(os.getenv("SCRAPE_INTERVAL_MINUTES", "30"))
MAX_NEWS_PER_RADAR      = int(os.getenv("MAX_NEWS_PER_RADAR", "8"))
NEWS_MAX_AGE_HOURS      = int(os.getenv("NEWS_MAX_AGE_HOURS", "6"))
DB_PATH                 = os.getenv("DB_PATH", "data/news.db")
TWSCRAPE_DB             = os.getenv("TWSCRAPE_DB", "data/accounts.db")
