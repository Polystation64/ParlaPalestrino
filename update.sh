#!/bin/bash
set -e
cd ~/parlaPalestrino
echo "[1/4] Parando servico..."
sudo systemctl stop parlapalestrino
echo "[2/4] Aplicando correcoes..."
python3 - << 'PY'
with open('/home/ubuntu/parlaPalestrino/bot.py', 'r') as f:
    lines = f.readlines()
in_diagnostico = False
result = []
changed = 0
for line in lines:
    if 'async def cmd_diagnostico' in line:
        in_diagnostico = True
    if 'async def cmd_twitter_setup' in line:
        in_diagnostico = False
    if in_diagnostico and 'parse_mode="Markdown"' in line:
        line = line.replace(', parse_mode="Markdown"', '')
        changed += 1
    result.append(line)
with open('/home/ubuntu/parlaPalestrino/bot.py', 'w') as f:
    f.writelines(result)
print(f"bot.py: {changed} linha(s) corrigida(s)")
PY
echo "[3/4] Atualizando dependencias..."
~/parlaPalestrino/venv/bin/pip install -q openai --upgrade
echo "[4/4] Iniciando servico..."
sudo systemctl start parlapalestrino
sleep 2
sudo systemctl is-active parlapalestrino && echo "SUCESSO — bot rodando!" || echo "ERRO — veja: sudo systemctl status parlapalestrino"
