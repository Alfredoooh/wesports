#!/bin/bash
# Instala cloudflared
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o cloudflared
chmod +x cloudflared

# Inicia Flask em background
gunicorn -w 2 -b 0.0.0.0:5000 api:app &

# Inicia tunnel
./cloudflared tunnel --url http://localhost:5000