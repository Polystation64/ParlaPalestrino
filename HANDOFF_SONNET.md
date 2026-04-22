# Handoff — ParlaPalestrino (de Opus 4.7 para Sonnet 4.6)

**Data:** 21/04/2026
**Usuário:** Alexandre (alexandre.phx@gmail.com)
**Pasta de trabalho:** `C:\Users\alexa\Downloads\GitHub\ParlaPalestrino`
**Servidor AWS:** `54.233.174.77` (acessível via SSH)

---

## O que é o projeto

Bot do Telegram "@ParlaPalestrino" que:
1. Coleta notícias do Palmeiras de RSS (Google News, UOL, Globo, etc.) + Twitter
2. Envia radares para o Telegram com as melhores manchetes
3. Publica tweets automáticos aprovados pelo dono (Alexandre)

**Arquitetura:**
- `scraper.py` — roda no servidor AWS, coleta RSS a cada X min
- `pc_twitter_collector.py` — roda no PC Windows do Alexandre (IP residencial, para não ser bloqueado pelo Twitter), envia tweets via HTTP POST para o servidor
- `receiver.py` — serviço no AWS que recebe tweets do PC na porta `8765` (token `parla2026verde`)
- `publisher.py` — posta tweets aprovados no @ParlaPalestrino
- `bot.py` — bot do Telegram (radar, aprovações)
- `db.sqlite` — banco com tabelas `news` e `pending_tweets`

**Serviços systemd no AWS:**
- `parlareciver` (receptor HTTP na 8765)
- `parlapalestrino` (bot principal)

---

## Onde paramos

### ✅ Feito nesta sessão

1. **og:image fallback no `scraper.py`** — RSS não traz imagem inline, então adicionei função `_og_image(url)` que busca o HTML da notícia e extrai `og:image`/`twitter:image` via regex. Resultado: 7/16 itens RSS agora têm imagem (antes 0/16). Deployado no AWS.

2. **Receiver estava crashando** (porta 8765 ocupada por processo zumbi PID 123037). Matamos e reiniciamos com `sudo systemctl restart parlareciver`. `/ping` responde externamente de novo.

3. **`pc_twitter_collector.py` reescrito para Scweet 5.3** — a lib mudou o schema: retorna dicts aninhados (`user.screen_name`, `media.image_links[]`) e campos sem sufixo `_count` (`likes`, `retweets`). O código antigo fazia `str(dict)` e gravava `Twitter @{'screen_name': 'LiAzeda'...}` no campo source. Também 0/113 tweets tinham imagem. Corrigido:
   - `user_obj = tweet.get("user") or {}` com `isinstance(user_obj, dict)` check
   - `username.strip().lstrip("@").replace(" ", "")[:50]` sanitização
   - `media_obj.get("image_links")` com fallback para `tweet.get("image_links")` (Scweet antigo)
   - `likes = int(tweet.get("likes") or tweet.get("likes_count") or ...)` — aceita ambos

4. **Arquivo `pc_twitter_collector.py` estava corrompido** no final (linha 188 tinha `}")` sobrando da última Edit tool). Acabei de remover essa linha. **Status atual: arquivo limpo, 187 linhas, sintaxe OK.**

### ⏳ Pendente (o usuário precisa executar)

1. **Rodar manualmente uma vez** no PowerShell do PC:
   ```powershell
   cd C:\Users\alexa\Downloads\GitHub\ParlaPalestrino
   python pc_twitter_collector.py
   ```
   Esperado: `[PC] ✅ Servidor: ~100 recebidos, ~100 novos.` sem erro de sintaxe.

2. **Configurar Windows Task Scheduler** para rodar o script a cada 30 min automaticamente (o Alexandre não configurou ainda — é por isso que ficou 4 dias sem tweets entrando no banco).

3. **Verificar no servidor** (que eu posso fazer via SSH autonomamente) que:
   - `pending_tweets` tem entries com `source = "Twitter @username (PC)"` limpo (sem dict serializado)
   - `image_url IS NOT NULL` para os top tweets
   - Próximo `/radar` no Telegram mistura Twitter + RSS + Agenda

### Tarefas abertas no todo list

- **Task #2** "Corrigir mapeamento de campos Scweet 5.3" — código está pronto, falta só o Alexandre rodar uma vez para validar. Pode marcar como `completed` quando confirmar.

---

## Coisas importantes para o Sonnet 4.6 saber

### Acesso

- **SSH no AWS:** funciona via `mcp__workspace__bash` (shell sandbox do Cowork). Servidor é `54.233.174.77`. Alexandre já tem chave SSH configurada — comandos tipo `ssh ubuntu@54.233.174.77 "..."` rodam diretamente.
- **PC Windows do Alexandre:** NÃO tenho acesso. Só ele pode executar `pc_twitter_collector.py`. Eu explico, ele roda.

### Gotchas do Scweet 5.3

```python
# Schema correto:
tweet = {
    "tweet_id": "1234",
    "user": {"screen_name": "foo", "name": "Foo Bar"},  # ← dict aninhado!
    "timestamp": "...",
    "text": "...",
    "embedded_text": "...",
    "likes": 123,          # ← sem _count
    "retweets": 45,        # ← sem _count
    "comments": 6,
    "media": {"image_links": ["https://..."]},  # ← imagens aqui, não no topo
    "tweet_url": "https://x.com/...",
    "raw": {...}
}
```

A biblioteca retorna via `tweet.model_dump()` (Pydantic v2), por isso vem como dict.

### Gotchas da ferramenta Edit/Write

- **Edit tool** às vezes trunca o final do arquivo (bug de cache). Sempre verifique o final com Read após edits grandes.
- **Write tool** também truncou uma vez no meio de uma f-string. Para arquivos grandes, prefiro Edit incremental.
- Se precisar patch rápido sem reescrever tudo, use bash: `printf '...' >> arquivo.py` ou `head -n N > /tmp/x && mv`.

### Mapeamento de paths (file tool ↔ bash)

| File tool (Windows path) | Bash (Linux mount) |
|---|---|
| `C:\Users\alexa\Downloads\GitHub\ParlaPalestrino\` | `/sessions/magical-trusting-bardeen/mnt/ParlaPalestrino/` |
| `C:\...\outputs` | `/sessions/magical-trusting-bardeen/mnt/outputs/` |
| `C:\...\uploads` | `/sessions/magical-trusting-bardeen/mnt/uploads/` (read-only) |

O mount do virtiofs às vezes demora 1-2s para sincronizar — se um Edit foi feito e o bash não vê, espera um pouco e tenta de novo.

---

## Próxima ação sugerida para o Sonnet 4.6

Quando o Alexandre voltar e disser "rodei o script", você deve:

1. **SSH no AWS** e rodar:
   ```bash
   ssh ubuntu@54.233.174.77 "sqlite3 /home/ubuntu/ParlaPalestrino/db.sqlite \"
     SELECT source, COUNT(*), SUM(CASE WHEN image_url IS NOT NULL THEN 1 ELSE 0 END) as with_img
     FROM pending_tweets
     WHERE created_at > datetime('now', '-1 hour')
     GROUP BY source
     ORDER BY COUNT(*) DESC LIMIT 20;
   \""
   ```
   Objetivo: ver se os sources estão limpos (`Twitter @handle (PC)`) e se `with_img > 0`.

2. Se tudo OK, **marcar Task #2 como completed** e avisar o Alexandre que o próximo `/radar` no Telegram já deve mostrar os tweets.

3. Lembrar ele de configurar o **Windows Task Scheduler** (passo a passo já foi dado em sessões anteriores — se ele não lembrar, refaça).

---

## Arquivos tocados nesta sessão

- `C:\Users\alexa\Downloads\GitHub\ParlaPalestrino\scraper.py` — adicionou `_og_image()`, deployado no AWS
- `C:\Users\alexa\Downloads\GitHub\ParlaPalestrino\pc_twitter_collector.py` — rewrite completo para Scweet 5.3, NÃO é deployado (roda no PC do Alexandre)

## Comandos úteis guardados

```bash
# Ver últimos tweets no banco do AWS:
ssh ubuntu@54.233.174.77 "sqlite3 /home/ubuntu/ParlaPalestrino/db.sqlite 'SELECT source, text, likes, image_url FROM pending_tweets ORDER BY created_at DESC LIMIT 10;'"

# Status dos serviços:
ssh ubuntu@54.233.174.77 "sudo systemctl status parlareciver parlapalestrino"

# Logs do receiver:
ssh ubuntu@54.233.174.77 "sudo journalctl -u parlareciver -n 50 --no-pager"

# Testar endpoint do receiver:
curl -s http://54.233.174.77:8765/ping

# Limpar tweets antigos com dados corrompidos:
ssh ubuntu@54.233.174.77 "sqlite3 /home/ubuntu/ParlaPalestrino/db.sqlite \"DELETE FROM pending_tweets WHERE source LIKE '%screen_name%';\""
```

---

**Tom com o Alexandre:** português BR, direto, sem enrolação. Ele é técnico, entende código. Prefere ver o output do comando ao invés de explicação longa. Ele está com poucos tokens, então seja econômico — respostas curtas e ações diretas.
