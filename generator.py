import json
from openai import OpenAI
from config import (
    GROQ_API_KEY, GROQ_MODEL,
    OPENROUTER_API_KEY, OPENROUTER_MODEL,
    OLLAMA_BASE_URL, OLLAMA_API_KEY, OLLAMA_MODEL,
    OPENAI_API_KEY, OPENAI_MODEL,
)

def _providers():
    p = []
    if GROQ_API_KEY:
        p.append(("Groq", OpenAI(api_key=GROQ_API_KEY, base_url="https://api.groq.com/openai/v1"), GROQ_MODEL))
    if OPENROUTER_API_KEY:
        p.append(("OpenRouter", OpenAI(api_key=OPENROUTER_API_KEY, base_url="https://openrouter.ai/api/v1", default_headers={"X-Title":"ParlaPalestrino"}), OPENROUTER_MODEL))
    if OLLAMA_API_KEY and OLLAMA_BASE_URL:
        p.append(("Ollama", OpenAI(api_key=OLLAMA_API_KEY, base_url=OLLAMA_BASE_URL), OLLAMA_MODEL))
    if OPENAI_API_KEY:
        p.append(("OpenAI", OpenAI(api_key=OPENAI_API_KEY), OPENAI_MODEL))
    return p

def _call(system, prompt):
    for name, client, model in _providers():
        try:
            print(f"[Generator] Tentando {name} ({model})...")
            resp = client.chat.completions.create(model=model, messages=[{"role":"system","content":system},{"role":"user","content":prompt}], max_tokens=1200, temperature=0.7)
            print(f"[Generator] OK com {name}.")
            return resp.choices[0].message.content.strip()
        except Exception as e:
            print(f"[Generator] {name} falhou: {e}")
    return None

_ENRICH_SYSTEM = """Você é editor do @ParlaPalestrino, conta informativa sobre o Palmeiras.
Analise cada notícia e devolva SOMENTE um JSON válido, sem markdown, sem explicações.
Para cada item retorne: rotulo (um de: "🚨 NOTÍCIA QUENTE"|"✅ CONFIRMADO"|"📌 CONTEXTO"|"⚽️ JOGO"|"💰 VALORES"|"🏆 MARCO"), titulo_curto (até 60 chars), o_que_e (1 frase, máx 80 chars), por_que_importa (1 frase, máx 80 chars), imagem (sugestão em 5 palavras), is_rumor (true/false)"""

def enrich_radar(items):
    if not items:
        return []
    news_list = "\n".join(f'{i+1}. {it["title"]} (fonte: {it["source"]})' for i,it in enumerate(items))
    prompt = f"""Analise estas {len(items)} notícias do Palmeiras e retorne um JSON array na mesma ordem:

{news_list}

Retorne SOMENTE o JSON array, sem markdown."""
    raw = _call(_ENRICH_SYSTEM, prompt)
    if not raw:
        return items
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"): raw = raw[4:]
    raw = raw.strip().rstrip("```").strip()
    try:
        enriched = json.loads(raw)
        return [{**items[i], **enriched[i]} if i < len(enriched) else items[i] for i in range(len(items))]
    except Exception as e:
        print(f"[Generator] Parse falhou: {e}")
        return items

_TWEET_SYSTEM = """Você é o redator do @ParlaPalestrino no Twitter/X.
Tom: diagnóstico informativo. Público: torcida do Palmeiras.
ESTRUTURA: 1ª linha emoji+fato | 2ª contexto | 3ª implicação prática | linha final 🗞 Fonte se relevante.
REGRAS: sempre começa com emoji | quebras de linha | máx 2 emojis | sem hashtags | sem opinião | rumor leva trava.
ENTREGUE: [A] Informativa  [B] Engajamento (pergunta)  [C] Explicador (3 linhas: aconteceu/muda/falta)
Máx 280 chars cada. SOMENTE as 3 versões."""

def generate_tweet(news_titles):
    if not news_titles:
        return []
    context = "\n".join(f"- {t}" for t in news_titles)
    prompt = f"Notícia(s):\n{context}\n\nGere [A] [B] [C]. Máx 280 chars cada."
    raw = _call(_TWEET_SYSTEM, prompt)
    if not raw:
        return []
    return [o[:280] for o in _parse(raw) if o][:3]

def _parse(text):
    options = []
    for marker in ["[A]","[B]","[C]"]:
        if marker not in text: continue
        start = text.index(marker)+len(marker)
        nexts = [text.index(m) for m in ["[A]","[B]","[C]"] if m in text and text.index(m)>start]
        end = min(nexts) if nexts else len(text)
        chunk = text[start:end].strip()
        if chunk: options.append(chunk)
    if len(options) >= 2: return options
    return [p.strip() for p in text.split("\n\n") if p.strip()][:3]
