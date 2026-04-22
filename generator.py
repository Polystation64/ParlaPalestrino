import json
from openai import OpenAI
from config import (
    GROQ_API_KEY, GROQ_MODEL,
    OPENROUTER_API_KEY, OPENROUTER_MODEL,
    OLLAMA_BASE_URL, OLLAMA_API_KEY, OLLAMA_MODEL,
    OPENAI_API_KEY, OPENAI_MODEL,
)

# Veículos cujo crédito "🗞️ Fonte:" aparece no rodapé do tweet.
_EDITORIAL_SOURCES = {
    "globo esporte": "ge",
    "ge":            "ge",
    "lance":         "Lance",
    "uol esporte":   "UOL",
    "espn brasil":   "ESPN",
    "estadão":       "Estadão",
    "folha":         "Folha",
    "google news":   None,    # genérico, não credita
    "agenda oficial": None,   # jogo — usa 📺 Transmissão
}


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


def _call(system, prompt, max_tokens=1400):
    for name, client, model in _providers():
        try:
            print(f"[Generator] Tentando {name} ({model})...")
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role":"system","content":system},{"role":"user","content":prompt}],
                max_tokens=max_tokens, temperature=0.7,
            )
            print(f"[Generator] OK com {name}.")
            return resp.choices[0].message.content.strip()
        except Exception as e:
            print(f"[Generator] {name} falhou: {e}")
    return None


_ENRICH_SYSTEM = """Você é editor do @ParlaPalestrino, conta informativa sobre o Palmeiras.
Analise cada notícia e devolva SOMENTE um JSON válido, sem markdown, sem explicações.
IMPORTANTE: escreva SEMPRE em português brasileiro com acentuação correta (ã, ç, é, ã, etc.).
Para cada item retorne: rotulo (um de: "🚨 NOTÍCIA QUENTE"|"✅ CONFIRMADO"|"📌 CONTEXTO"|"⚽️ JOGO"|"💰 VALORES"|"🏆 MARCO"), titulo_curto (até 60 chars), o_que_e (1 frase clara e específica, máx 80 chars — descreva o fato concreto, nunca frases genéricas como "informação sobre jogador"), por_que_importa (1 frase, máx 80 chars), imagem (sugestão em 5 palavras), is_rumor (true/false)"""


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


# ─────────────────────────────────────────────
# TWEET GENERATION (formato editorial @ParlaPalestrino)
# ─────────────────────────────────────────────
_TWEET_SYSTEM = """Você é o redator do @ParlaPalestrino no Twitter/X, conta verificada (X Premium — texto longo liberado).
Tom: diagnóstico informativo, sem opinião emotiva do narrador. Público: torcida adulta e engajada do Palmeiras.

FORMATO OBRIGATÓRIO (siga exatamente):
Linha 1: emoji temático + gancho forte (1 frase com o fato principal).
Linha em branco.
1-2 parágrafos (2-4 frases cada) com contexto + implicação prática para o clube, elenco ou torcida.
Linha em branco.
Rodapé (condicional):
  - Se CREDITO_FONTE for fornecido, inclua: 🗞️ Fonte: {CREDITO_FONTE}
  - Se TRANSMISSAO for fornecido (jogo), inclua: 📺 Transmissão: {TRANSMISSAO}
  - Se TEM_IMAGEM=sim, inclua uma última linha: 📸 Reprodução

EMOJI INICIAL (escolha UM, baseado no teor do assunto):
🚨 lesão, baixa, alerta crítico, STJD
⚽️ jogo, agenda oficial, convocação, escalação
✅ confirmação oficial
💰 ou 🤑 valores, contratos, naming rights, dinheiro, rescisão
🏆 título, marco histórico, final, conquista
📰 notícia factual geral
🎯 estratégia, análise tática, esquema
🔄 renovação, transferência, troca

REGRAS:
- Entre 280 e 900 caracteres TOTAL (X Premium aceita texto longo).
- Sempre quebras de linha DUPLAS entre gancho, corpo e rodapé.
- Sem hashtags.
- Sem opinião do narrador ("acho", "adoro", "torço"). Diagnóstico neutro.
- Rumor: usar trava explícita ("ainda não é confirmado", "informação em verificação").
- Máximo 2 emojis no corpo (fora do rodapé e do inicial).
- NÃO repita palavras do título no gancho se soar redundante — reescreva em tom editorial.

ENTREGUE 3 VERSÕES, SOMENTE estas, cada uma começando com o marcador em colchete:
[A] Informativa — foca em fato + contexto + implicação.
[B] Engajamento — mesma estrutura, terminando com 1 pergunta curta à torcida (ANTES do rodapé).
[C] Explicador — organizado em 3 mini-seções: "Aconteceu:", "Muda:", "Falta:" (ou "Observar:"). Cada uma em 1-2 linhas.

NADA além das 3 versões. Não explique, não comente, não use markdown."""


def generate_tweet(items_or_titles, image_url: str | None = None):
    """
    Gera 3 versões de tweet. Aceita lista de dicts (preferido) ou lista de strings (retro-compat).

    Se receber dicts, extrai source/transmissao/image para construir o rodapé contextual.
    """
    if not items_or_titles:
        return []

    # Retro-compatibilidade: lista de strings.
    if isinstance(items_or_titles[0], str):
        titles    = list(items_or_titles)
        sources   = []
        transmissao = None
        has_image = bool(image_url)
    else:
        titles      = [it["title"] for it in items_or_titles]
        sources     = [it.get("source","") for it in items_or_titles]
        has_image   = bool(image_url) or any(it.get("image_url") for it in items_or_titles)
        # Tenta extrair transmissão do título de Agenda Oficial.
        transmissao = None
        for it in items_or_titles:
            if it.get("source") == "Agenda Oficial":
                t = it.get("title","")
                # formato: "⚽️ JOGO HOJE: Palmeiras x X — HH:MM (COMP) | TRANSMISSAO"
                if "|" in t:
                    transmissao = t.rsplit("|", 1)[-1].strip()
                break

    # Monta crédito: pega a primeira fonte editorial reconhecida.
    credito_fonte = None
    for s in sources:
        key = (s or "").strip().lower()
        if key in _EDITORIAL_SOURCES:
            credito_fonte = _EDITORIAL_SOURCES[key]
            if credito_fonte:
                break

    context = "\n".join(f"- {t}" for t in titles)

    ctx_parts = []
    if credito_fonte:
        ctx_parts.append(f"CREDITO_FONTE: {credito_fonte}")
    if transmissao and transmissao.lower() not in ("a confirmar",""):
        ctx_parts.append(f"TRANSMISSAO: {transmissao}")
    ctx_parts.append(f"TEM_IMAGEM: {'sim' if has_image else 'nao'}")
    ctx_block = "\n".join(ctx_parts)

    prompt = f"""Notícia(s):
{context}

Contexto para o rodapé:
{ctx_block}

Gere [A], [B] e [C] seguindo ESTRITAMENTE o formato do system prompt (entre 280 e 900 chars cada, com rodapé apropriado)."""

    raw = _call(_TWEET_SYSTEM, prompt, max_tokens=1800)
    if not raw:
        return []
    return [o[:1500] for o in _parse(raw) if o][:3]


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
