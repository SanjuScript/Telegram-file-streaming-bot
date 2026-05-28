import os
import json
import logging
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

logger = logging.getLogger(__name__)

# Base directories
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")

def load_settings():
    """Load settings from settings.json file."""
    os.makedirs(DATA_DIR, exist_ok=True)
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                data = json.load(f)
                # Ensure structure is upgraded with new keys
                if "favorites" not in data:
                    data["favorites"] = []
                if "history" not in data:
                    data["history"] = []
                return data
        except Exception as e:
            logger.error(f"Error loading settings file: {e}")
    # Default settings
    return {
        "private_mode": True, 
        "total_links_generated": 0,
        "favorites": [],
        "history": []
    }

def save_settings(settings):
    """Save settings to settings.json file."""
    os.makedirs(DATA_DIR, exist_ok=True)
    try:
        with open(SETTINGS_FILE, "w") as f:
            json.dump(settings, f, indent=4)
    except Exception as e:
        logger.error(f"Error saving settings file: {e}")

class Config:
    # Telegram settings
    BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8971606356:AAE5DiuJjBgpq0c0Twi_Ji_GuGqBi1Vw_zc")
    if not BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN must be set in environment or .env file.")
        
    OWNER_ID = int(os.getenv("OWNER_ID", "1948015235"))
    
    # Telethon MTProto credentials
    API_ID = int(os.getenv("API_ID", "30915176"))
    API_HASH = os.getenv("API_HASH", "6bdd3f6dbec3acbd6a55178ea21f397e")
        
    # Allowed users - comma separated list of user IDs or usernames (without @)
    # e.g., ALLOWED_USERS=12345678,sanju_script
    _allowed_users_raw = os.getenv("ALLOWED_USERS", "")
    ALLOWED_USERS = set()
    if _allowed_users_raw:
        for user in _allowed_users_raw.split(","):
            user = user.strip()
            if not user:
                continue
            try:
                ALLOWED_USERS.add(int(user))
            except ValueError:
                ALLOWED_USERS.add(user.lower())

    # FastAPI Streaming Server settings
    SERVER_URL = os.getenv("SERVER_URL", "http://localhost:8000").rstrip("/")
    HOST = os.getenv("HOST", "0.0.0.0")
    PORT = int(os.getenv("PORT", "8000"))

    # Local Telegram Bot API Server configurations (optional)
    TELEGRAM_BASE_URL = os.getenv("TELEGRAM_BASE_URL")
    TELEGRAM_BASE_FILE_URL = os.getenv("TELEGRAM_BASE_FILE_URL")
    TELEGRAM_LOCAL_MODE = os.getenv("TELEGRAM_LOCAL_MODE", "true").lower() in ("true", "1", "yes")

    # Local Bot API Server cache storage path on Xubuntu
    TELEGRAM_FILES_DIR = f"/var/lib/telegram-bot-api/bot{BOT_TOKEN}"

    # App Log Level
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

    @classmethod
    def get_private_mode(cls) -> bool:
        """Get the current private mode status (Default: True)."""
        settings = load_settings()
        return settings.get("private_mode", True)

    @classmethod
    def set_private_mode(cls, private: bool) -> None:
        """Set the private mode status."""
        settings = load_settings()
        settings["private_mode"] = private
        save_settings(settings)
        logger.info(f"Private mode updated to: {private}")

    @classmethod
    def get_total_links(cls) -> int:
        """Get total links generated from statistics."""
        settings = load_settings()
        return settings.get("total_links_generated", 0)

    @classmethod
    def increment_links(cls) -> int:
        """Increment the generated links count by 1 and return the new value."""
        settings = load_settings()
        current = settings.get("total_links_generated", 0)
        new_val = current + 1
        settings["total_links_generated"] = new_val
        save_settings(settings)
        return new_val

    @classmethod
    def get_favorites(cls) -> list[int]:
        """Get list of Telegram User IDs present in the favorites list."""
        settings = load_settings()
        return settings.get("favorites", [])

    @classmethod
    def add_favorite(cls, user_id: int) -> bool:
        """Add a User ID to the favorites list. Returns True if added, False if already exists."""
        settings = load_settings()
        favorites = settings.setdefault("favorites", [])
        if user_id not in favorites:
            favorites.append(user_id)
            save_settings(settings)
            return True
        return False

    @classmethod
    def remove_favorite(cls, user_id: int) -> bool:
        """Remove a User ID from the favorites list. Returns True if removed, False if not found."""
        settings = load_settings()
        favorites = settings.setdefault("favorites", [])
        if user_id in favorites:
            favorites.remove(user_id)
            save_settings(settings)
            return True
        return False

    @classmethod
    def add_request_log(cls, user_id: int) -> None:
        """Log a stream link request timestamp for analytics, automatically purging logs older than 30 days."""
        import time
        settings = load_settings()
        history = settings.setdefault("history", [])
        
        # Append current request details
        history.append({
            "timestamp": int(time.time()),
            "user_id": user_id
        })
        
        # Purge logs older than 30 days to limit settings.json size growth
        thirty_days_ago = int(time.time()) - 2592000
        settings["history"] = [entry for entry in history if entry.get("timestamp", 0) > thirty_days_ago]
        
        save_settings(settings)

    @classmethod
    def get_weekly_analytics(cls) -> dict:
        """Get the count of files generated in the last 24 hours and the last 7 days (weekly stats)."""
        import time
        settings = load_settings()
        history = settings.get("history", [])
        now = int(time.time())
        
        one_day_ago = now - 86400
        seven_days_ago = now - 604800
        
        links_24h = sum(1 for entry in history if entry.get("timestamp", 0) > one_day_ago)
        links_7d = sum(1 for entry in history if entry.get("timestamp", 0) > seven_days_ago)
        
        return {
            "links_24h": links_24h,
            "links_7d": links_7d
        }
