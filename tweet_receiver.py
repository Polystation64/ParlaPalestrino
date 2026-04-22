"""
tweet_receiver.py

Mini servidor HTTP que roda na VPS e recebe tweets
coletados pelo script do PC (IP residencial).
Salva direto no banco de dados do bot.

Porta: 8765 (interna, não exposta publicamente sem token)
"""

import json
import hashlib
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timezone
from db import init_db, save_news
from config import RECEIVER_TOKEN

class TweetReceiver(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        pass  # silencia logs HTTP padrão

    def do_POST(self):
        # Valida token de segurança
        token = self.headers.get("X-Bot-Token", "")
        if token != RECEIVER_TOKEN:
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b'{"error": "unauthorized"}')
            return

        if self.path != "/tweets":
            self.send_response(404)
            self.end_headers()
            return

        try:
            length = int(self.headers.get("Content-Length", 0))
            body   = self.rfile.read(length)
            tweets = json.loads(body)

            # Normaliza e salva
            items = []
            for t in tweets:
                url  = t.get("url", "")
                if not url:
                    continue
                    
                raw_pub = t.get("published_at")
                pub = None
                if raw_pub:
                    try:
                        if isinstance(raw_pub, (int, float)) or (isinstance(raw_pub, str) and str(raw_pub).isdigit()):
                            pub = datetime.fromtimestamp(float(raw_pub), timezone.utc).isoformat()
                        elif isinstance(raw_pub, str):
                            if len(raw_pub.split()) == 6 and "+0000" in raw_pub:
                                pub = datetime.strptime(raw_pub, "%a %b %d %H:%M:%S %z %Y").astimezone(timezone.utc).isoformat()
                            elif raw_pub.endswith("Z") or "T" in raw_pub:
                                pub = raw_pub 
                    except Exception:
                        pass
                if not pub:
                    pub = datetime.now(timezone.utc).isoformat()

                items.append({
                    "hash":         hashlib.md5(url.encode()).hexdigest(),
                    "title":        t.get("text", "")[:300],
                    "url":          url,
                    "source":       t.get("source", "Twitter PC"),
                    "published_at": pub,
                    "score":        t.get("score", 10),
                    "image_url":    t.get("image_url"),
                })

            saved = save_news(items)
            print(f"[Receiver] {len(items)} tweets recebidos, {saved} novos salvos.")

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"saved": saved, "total": len(items)}).encode())

        except Exception as e:
            print(f"[Receiver] Erro: {e}")
            self.send_response(500)
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())

    def do_GET(self):
        # Health check simples
        if self.path == "/ping":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"status": "ok"}')
        else:
            self.send_response(404)
            self.end_headers()


def run_receiver(port: int = 8765):
    init_db()
    server = HTTPServer(("0.0.0.0", port), TweetReceiver)
    print(f"[Receiver] Escutando na porta {port}...")
    server.serve_forever()


if __name__ == "__main__":
    run_receiver()
