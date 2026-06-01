#!/bin/bash
# =============================================================================
# Auto-Start Script for Telegram File Streaming Bot
# Handles Cloudflare tunnel + bot startup automatically on every reboot.
# No manual URL updating needed!
# =============================================================================

cd "$(dirname "$0")"

BOT_PORT=8082
ENV_FILE=".env"
TUNNEL_CONTAINER_NAME="cloudflare-tunnel"
BOT_CONTAINER_NAME="telegram-stream-bot"

echo "🚀 Starting Telegram Streaming Bot System..."

# --- Step 1: Stop old containers ---
echo "🛑 Cleaning up old containers..."
docker rm -f "$TUNNEL_CONTAINER_NAME" 2>/dev/null || true
docker rm -f "$BOT_CONTAINER_NAME" 2>/dev/null || true

# --- Step 2: Start Cloudflare Tunnel ---
echo "🌐 Starting Cloudflare Tunnel..."
docker run -d \
  --name "$TUNNEL_CONTAINER_NAME" \
  --network host \
  --restart unless-stopped \
  cloudflare/cloudflared:latest --no-autoupdate tunnel --url http://localhost:$BOT_PORT

# --- Step 3: Wait for tunnel URL to appear ---
echo "⏳ Waiting for tunnel URL (up to 30 seconds)..."
TUNNEL_URL=""
for i in $(seq 1 30); do
  TUNNEL_URL=$(docker logs "$TUNNEL_CONTAINER_NAME" 2>&1 | grep -oP 'https://[a-z0-9-]+\.trycloudflare\.com' | head -1)
  if [ -n "$TUNNEL_URL" ]; then
    break
  fi
  sleep 1
done

if [ -z "$TUNNEL_URL" ]; then
  echo "❌ Failed to get tunnel URL after 30 seconds. Check: docker logs $TUNNEL_CONTAINER_NAME"
  exit 1
fi

echo "✅ Tunnel URL: $TUNNEL_URL"

# --- Step 4: Update .env with new URL ---
echo "📝 Updating .env with new tunnel URL..."
if grep -q "SERVER_URL=" "$ENV_FILE"; then
  sed -i "s|SERVER_URL=.*|SERVER_URL=$TUNNEL_URL|" "$ENV_FILE"
else
  echo "SERVER_URL=$TUNNEL_URL" >> "$ENV_FILE"
fi

echo "✅ .env updated: $(grep SERVER_URL $ENV_FILE)"

# --- Step 5: Start the Bot ---
echo "🤖 Starting Telegram Stream Bot..."
docker run -d \
  --name "$BOT_CONTAINER_NAME" \
  --restart unless-stopped \
  --network host \
  --env-file "$ENV_FILE" \
  -v youtube-downloader_telegram-bot-api-data:/var/lib/telegram-bot-api \
  -v "$(pwd)/data:/app/data" \
  -v "$(pwd)/.env:/app/.env" \
  telegram-stream-bot

echo ""
echo "============================================="
echo "✅ Everything is running!"
echo "🌐 Tunnel URL: $TUNNEL_URL"
echo "🤖 Bot Container: $BOT_CONTAINER_NAME"
echo "============================================="
echo ""
echo "📋 Bot logs: docker logs -f $BOT_CONTAINER_NAME"
echo "🌐 Tunnel logs: docker logs -f $TUNNEL_CONTAINER_NAME"
