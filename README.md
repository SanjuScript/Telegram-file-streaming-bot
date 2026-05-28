# Telegram Stream Link Generator Bot

A lightweight, secure, and private Telegram Bot that receives video, audio, or document files and generates playable, range-aware streaming links. These links can be played directly in media players like **VLC**, **MX Player**, **IPTV players**, **browsers**, and other online stream-compatible players.

## How It Works

1. **User Sends Media**: You upload or forward a video, audio, or document file to the Telegram bot.
2. **Access Control**: The bot verifies that your Telegram User ID or Username is authorized (`ALLOWED_USERS`).
3. **Secure Proxy Generation**: The bot retrieves the internal file path from Telegram and generates a secure link mapping to a local FastAPI server (e.g. `http://<your-server-ip>:8000/stream/<file_id>/<file_name>`).
4. **No Token Exposure**: The FastAPI server proxies download requests directly to Telegram's file server. **Your bot token is never exposed to the client or media players.**
5. **Seeking Support (Range Requests)**: The FastAPI server forwards HTTP `Range` headers, enabling video seeking/scrubbing in players like VLC and MX Player out-of-the-box.

---

## Folder Structure

```
telegram-stream-bot/
│
├── app/
│   ├── main.py            # Entry point, FastAPI startup & lifespan hook
│   ├── handlers.py        # Bot command and media message handlers
│   ├── telegram_utils.py  # Bot configuration and security checks
│   └── config.py          # Environment configuration loading
│
├── requirements.txt       # Python dependencies
├── Dockerfile             # Container configuration
├── .env                   # Configuration variables (tokens, IPs, settings)
└── README.md              # Setup and deployment guide
```

---

## Configuration (`.env`)

Create a `.env` file in the root directory (based on the template):

```env
# Telegram Bot Token (Get it from @BotFather on Telegram)
TELEGRAM_BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ

# Allowed Users (Comma-separated list of User IDs or Usernames allowed to use the bot)
# Example: ALLOWED_USERS=987654321,my_telegram_username
# Leave empty to allow ALL users (Not recommended!)
ALLOWED_USERS=987654321,my_telegram_username

# Public URL where the streaming server is accessible.
# VLC, MX Player, etc. will stream using links based on this URL.
SERVER_URL=http://192.168.1.100:8000

# Server network bindings
HOST=0.0.0.0
PORT=8000

# Custom Telegram Bot API Base URLs (Optional - for local Telegram Bot API Server)
# Required to support streaming files > 20MB.
# TELEGRAM_BASE_URL=http://localhost:8081/bot
# TELEGRAM_BASE_FILE_URL=http://localhost:8081/file/bot

# Application Log Level (DEBUG, INFO, WARNING, ERROR)
LOG_LEVEL=INFO
```

---

## Local Setup & Run

### 1. Prerequisites
- Python 3.10 or higher
- An internet-facing IP or LAN IP (for home server usage)

### 2. Installation
```bash
# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install requirements
pip install -r requirements.txt
```

### 3. Run the application
```bash
python -m app.main
```
The FastAPI server will start, and the Telegram bot will start polling for messages concurrently.

---

## Docker Deployment (Xubuntu Server)

Perfect for self-hosting on a home server.

### 1. Build the Docker Image
```bash
docker build -t telegram-stream-bot .
```

### 2. Run the Container
Run the container with automatic restart enabled:
```bash
docker run -d \
  --name telegram-stream-bot \
  --restart unless-stopped \
  --env-file .env \
  -p 8000:8000 \
  telegram-stream-bot
```

### 3. Docker Compose (Alternative)
If you prefer Docker Compose, create a `docker-compose.yml` file in the root:
```yaml
version: '3.8'

services:
  stream-bot:
    build: .
    container_name: telegram-stream-bot
    restart: unless-stopped
    ports:
      - "8000:8000"
    env_file:
      - .env
```
Start the container in the background:
```bash
docker compose up -d
```

---

## Streaming in Media Players

When the bot sends you a stream link, copy it and load it into your player:

*   **VLC**:
    - Open VLC -> **File** -> **Open Network...** (macOS) or **Media** -> **Open Network Stream...** (Windows/Linux).
    - Paste the link and press **Play/Open**.
*   **MX Player**:
    - Tap menu -> **Network Stream**.
    - Paste the link and tap **OK**.
*   **Browser**:
    - Paste the URL directly into the address bar to watch directly (dependent on the browser supporting the video format/codec).

---

## ⚠️ Standard Telegram API 20MB Limitation

When using Telegram's default public servers (`api.telegram.org`), the bot API restricts downloads via `getFile` to **20MB**. Files larger than 20MB will return a "File is too big" error from the Telegram Bot API.

### Solution: Local Telegram Bot API Server
To stream files up to **2GB** (e.g., movies), you can run a **Local Telegram Bot API Server** on your self-hosted server:
1. Run the local server container (see [Telegram Bot API Server Docker](https://hub.docker.com/r/aiogram/telegram-bot-api)).
2. Configure `TELEGRAM_BASE_URL` and `TELEGRAM_BASE_FILE_URL` in your `.env` file pointing to your local instance (e.g., `http://localhost:8081/bot` and `http://localhost:8081/file/bot`).
3. Set your bot's token on the local server, and start streaming large media files immediately!
