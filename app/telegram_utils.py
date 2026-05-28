import os
import logging
from telegram.ext import Application, ApplicationBuilder
from telethon import TelegramClient
from app.config import Config

logger = logging.getLogger(__name__)

def get_telethon_client() -> TelegramClient:
    """
    Build and return the Telethon TelegramClient instance logged in as a Bot.
    Session is stored persistently in the data directory.
    """
    session_path = os.path.join(Config.DATA_DIR, "telethon_session")
    logger.info(f"Initializing Telethon TelegramClient at session path: {session_path}")
    return TelegramClient(
        session_path,
        Config.API_ID,
        Config.API_HASH
    )

def get_telegram_app() -> Application:
    """
    Build and return the python-telegram-bot Application instance.
    """
    builder = ApplicationBuilder().token(Config.BOT_TOKEN)
    
    # Configure custom base URLs if running a local Bot API Server (supports files > 20MB)
    if Config.TELEGRAM_BASE_URL:
        logger.info(f"Using custom Telegram Base URL: {Config.TELEGRAM_BASE_URL}")
        builder.base_url(Config.TELEGRAM_BASE_URL)
    if Config.TELEGRAM_BASE_FILE_URL:
        logger.info(f"Using custom Telegram Base File URL: {Config.TELEGRAM_BASE_FILE_URL}")
        builder.base_file_url(Config.TELEGRAM_BASE_FILE_URL)
        
    # Enable local mode if bot runs on the same machine/shared filesystem as local Bot API Server
    if Config.TELEGRAM_BASE_URL and Config.TELEGRAM_LOCAL_MODE:
        logger.info("Enabling local mode for file path retrieval.")
        builder.local_mode(True)
        
    return builder.build()

def is_user_allowed(user_id: int, username: str = None) -> bool:
    """
    Check if the user is authorized to use the bot.
    - Owner (Config.OWNER_ID) is ALWAYS allowed.
    - If private mode is True, only allow:
      1. The Owner/Developer.
      2. Any User ID present in the favorites list.
      3. Any User ID/username configured in ALLOWED_USERS.
    - If private mode is False (Public), allow everyone.
    """
    # 1. Owner/Developer is always allowed
    if user_id == Config.OWNER_ID:
        return True

    # 2. Check if private/restricted mode is active
    if Config.get_private_mode():
        # Check if user is in favorites list
        if user_id in Config.get_favorites():
            return True
            
        # Check if user is in environment ALLOWED_USERS
        if user_id in Config.ALLOWED_USERS:
            return True
        if username and username.lower() in Config.ALLOWED_USERS:
            return True
            
        return False

    # 3. If in public mode, allow everyone
    return True
