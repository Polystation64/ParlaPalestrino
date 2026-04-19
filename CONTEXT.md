# ParlaPalestrino Bot — Contexto do Projeto

## O que é
Bot automatizado para a conta [@ParlaPalestrino](https://x.com/ParlaPalestrino) no Twitter/X.
Monitora notícias do Palmeiras, apresenta um radar editorial via Telegram e posta tweets aprovados pelo usuário.

**Dono:** Alexandre Ieva (@alexandre no Telegram, ID: 8151185500)

---

## Arquitetura geral

```
[PC do Alexandre - IP residencial]
  pc_twitter_collector.py (roda a cada 30min via Agendador de Tarefas)
  → busca tweets sobre Palmeiras via Scweet
  → envia para o servidor via HTTP POST na porta 8765

[Servidor AWS - Ubuntu 24.04 - 54.233.174.77]
  tweet_receiver.py   → recebe tweets do PC e salva no SQLite
  scraper.py          → coleta RSS (GE, Lance, UOL, ESPN) + agenda oficial
  generator.py        → gera tweets via AI (fallback: Groq → OpenRouter → Ollama → OpenAI)
  bot.py              → Telegram bot + scheduler APScheduler (radar a cada 30min)
  publisher.py        → posta no Twitter via Tweepy API v2
  db.py               → SQLite helpers
  config.py           → carrega variáveis do .env
  scraper_twitter.py  → monitoramento de timelines (98 perfis, usado como fallback)
```

---

## Por que o Twitter roda no PC e não no servidor

O Twitter/X bloqueia IPs de data center (AWS, DigitalOcean etc.) no nível de rede.
Qualquer busca via SearchTimeline de IP de servidor retorna 404 imediatamente.
A solução foi rodar o coletor no PC do Alexandre (IP residencial), que não é bloqueado.
O servidor recebe os tweets coletados via HTTP na porta 8765 (receiver).

---

## Fluxo completo

1. `pc_twitter_collector.py` roda no PC a cada 30min
   - Usa Scweet com cookies da conta `@oscardashopee` (conta fantasma, não a principal)
   - Apaga `scweet_state.db` antes de cada run para resetar limite diário
   - Busca 4 queries: `#Palmeiras`, `Palmeiras min_faves:100`, `Verdão OR Alviverde`, combinadas
   - Envia JSON para `http://54.233.174.77:8765/tweets` com header `X-Bot-Token: parla2026verde`

2. `tweet_receiver.py` roda como serviço systemd (`parlareciver`)
   - Escuta na porta 8765
   - Valida o token de segurança
   - Salva tweets no SQLite (`data/news.db`)

3. `bot.py` roda como serviço systemd (`parlapalestrino`)
   - Scheduler APScheduler dispara `run_radar_cycle` a cada 30min
   - Coleta RSS + agenda oficial do Palmeiras
   - Busca top 8 notícias no banco (filtradas por `published_at` das últimas 6h)
   - Chama `enrich_radar()` no `generator.py` — UMA chamada AI para enriquecer todos os itens
   - Envia radar formatado para o Telegram do Alexandre

4. Alexandre responde `C1`, `C2` etc. no Telegram
   - Bot chama `generate_tweet()` com as notícias escolhidas
   - Retorna 3 versões: [A] Informativa, [B] Engajamento, [C] Explicador
   - Alexandre aprova, edita ou descarta via botões inline
   - Bot posta no @ParlaPalestrino via Tweepy

---

## Serviços systemd

| Serviço | Arquivo | Descrição |
|---|---|---|
| `parlapalestrino` | `bot.py` | Bot principal + scheduler |
| `parlareciver` | `tweet_receiver.py` | Receiver de tweets do PC |

Comandos: `sudo systemctl start/stop/restart/status parlapalestrino`

---

## Variáveis de ambiente (.env)

```
TELEGRAM_BOT_TOKEN      # token do bot @ParlaPalestrinoBOT
TELEGRAM_CHAT_ID        # ID do chat do Alexandre (8151185500)

TWITTER_API_KEY         # Consumer Key do app @ParlaPalestrino
TWITTER_API_SECRET      # Consumer Secret
TWITTER_ACCESS_TOKEN    # Access Token (Read+Write)
TWITTER_ACCESS_SECRET   # Access Token Secret

SCRAPER_TWITTER_USER    # conta fantasma para twscrape (Palmeirens99158)
SCRAPER_TWITTER_PASS    # senha
SCRAPER_TWITTER_EMAIL   # email da conta fantasma
SCRAPER_TWITTER_EMAIL_PASS

GROQ_API_KEY            # provider principal de AI (gratuito)
GROQ_MODEL              # llama-3.3-70b-versatile
OPENROUTER_API_KEY      # fallback 2
OPENROUTER_MODEL        # google/gemma-4-31b-it:free
OLLAMA_BASE_URL         # fallback 3
OLLAMA_API_KEY
OLLAMA_MODEL
OPENAI_API_KEY          # fallback 4 (vazio, sem acesso ainda)
OPENAI_MODEL            # gpt-4o

RECEIVER_TOKEN          # parla2026verde (segurança do endpoint HTTP)
SCRAPE_INTERVAL_MINUTES # 30
MAX_NEWS_PER_RADAR      # 8
NEWS_MAX_AGE_HOURS      # 6
```

---

## Banco de dados (SQLite — data/news.db)

**Tabela `news`:**
- `id, hash, title, url, source, published_at, score, image_url, tweeted, created_at`
- `tweeted=0` = disponível para radar
- Filtro: `published_at > now - 6h` (exceto Agenda Oficial)
- Score: keywords Palmeiras (+10), jogadores (+5), palavras-chave quentes (+3), engajamento Twitter (+2 a +15)

**Tabela `pending_tweets`:**
- `id, news_ids, tweet_text, image_url, status, created_at`
- Status: `pending` → `posted` ou `discarded`

---

## Fontes de notícias

**RSS (servidor):**
- Globo Esporte Palmeiras, Lance, UOL Esporte, ESPN Brasil, Google News

**API Oficial Palmeiras:**
- `apiverdao.palmeiras.com.br/wp-json/apiverdao/v1/jogos-mes`
- Fallback: ESPN API pública

**Twitter (PC do Alexandre):**
- Scweet com conta `@oscardashopee`
- 4 queries a cada ciclo de 30min
- Enviado ao servidor via receiver na porta 8765

**98 perfis monitorados (scraper_twitter.py):**
- Oficiais: @Palmeiras, @AllianzParque, @geverdao, @lance_palmeiras etc.
- Jornalistas/setoristas: @GuiVXavier, @camilac_alves, @reporterfragoso etc.
- Fan accounts: @siamopalestra, @Espiaoverde, @mundopalmeiras etc.
- Jogadores: @Flaco_Lopez42, @gustavogomez462 etc.

---

## Sistema editorial (parla-copy-chief)

Tweets seguem o padrão editorial do @ParlaPalestrino:
- Tom: diagnóstico informativo, sem opinião do narrador
- Estrutura: GANCHO → FATO → IMPACTO → SERVIÇO
- Sempre começa com emoji
- Quebras de linha para legibilidade
- Máximo 2 emojis, sem hashtags (ou 1 se natural)
- Rumor: trava explícita ("ainda não é fechado")
- Fonte só se for veículo relevante (GE, Lance, ESPN, Estadão)

3 versões sempre geradas:
- [A] Informativa — direta, fatos
- [B] Engajamento — pergunta para a torcida comentar
- [C] Explicador — o que aconteceu / o que muda / o que falta definir

---

## GitHub

Repositório: `https://github.com/Polystation64/ParlaPalestrino` (privado)

**Deploy:**
```bash
# No PC: commit + push pelo GitHub Desktop
# No servidor:
bash ~/parlaPalestrino/update.sh
```

O `update.sh` faz: stop → git pull → pip install → start

---

## Problemas conhecidos e soluções

| Problema | Causa | Solução |
|---|---|---|
| SearchTimeline 404 | IP AWS bloqueado pelo Twitter | PC collector com Scweet |
| Scweet esgota limite | Contador diário da lib | Apaga `scweet_state.db` antes de cada run |
| Radar não aparece | `new_count=0` bloqueava | Removida checagem, sempre mostra top 8 |
| @unknown no source | Campo errado do Scweet | Usar `tweet.get("username")` |
| Notícias antigas no radar | Filtro usava `created_at` | Corrigido para filtrar por `published_at` |
| Receiver porta em uso | nohup + systemd duplicado | Matar processo manual antes do systemd |

---

## Comandos úteis no servidor

```bash
# Ver logs
tail -f ~/parlaPalestrino/data/bot.log
tail -f ~/parlaPalestrino/data/receiver.log

# Status dos serviços
sudo systemctl status parlapalestrino
sudo systemctl status parlareciver

# Verificar tweets no banco
python3 -c "
import sqlite3
conn = sqlite3.connect('/home/ubuntu/parlaPalestrino/data/news.db')
c = conn.cursor()
c.execute(\"SELECT count(*) FROM news WHERE tweeted=0\")
print('Disponíveis:', c.fetchone()[0])
c.execute(\"SELECT source, count(*) FROM news GROUP BY source ORDER BY 2 DESC LIMIT 10\")
for r in c.fetchall(): print(r)
conn.close()
"

# Testar receiver
curl http://localhost:8765/ping

# Atualizar código
bash ~/parlaPalestrino/update.sh
```
