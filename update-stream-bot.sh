#!/bin/bash
# Helper script to update, rebuild, and inspect logs of the Telegram File Streaming Bot

# Navigate to the directory containing this script (ensures it runs from the correct folder)
cd "$(dirname "$0")"

echo "🔄 Pulling latest changes from Git..."
git pull origin main

echo "🛑 Stopping and removing the old telegram-stream-bot container..."
docker rm -f telegram-stream-bot 2>/dev/null || true

echo "🐳 Rebuilding the telegram-stream-bot image..."
docker build -t telegram-stream-bot .

echo "🚀 Starting the telegram-stream-bot container..."
docker run -d \
  --name telegram-stream-bot \
  --restart unless-stopped \
  --network host \
  --env-file .env \
  -v youtube-downloader_telegram-bot-api-data:/var/lib/telegram-bot-api \
  -v "$(pwd)/data:/app/data" \
  telegram-stream-bot

echo "📋 Showing logs (Press Ctrl+C to exit logs view)..."
docker logs -f telegram-stream-bot
