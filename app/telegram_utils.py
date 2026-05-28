import logging
from telegram.ext import Application, ApplicationBuilder
from app.config import Config

logger = logging.getLogger(__name__)

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
    - If private mode is True, only allow the Owner and any users configured in ALLOWED_USERS.
    - If private mode is False (Public), allow everyone.
    """
    # 1. Owner is always allowed
    if user_id == Config.OWNER_ID:
        return True

    # 2. Check if private mode is enabled
    if Config.get_private_mode():
        # Only allow explicitly authorized users
        if user_id in Config.ALLOWED_USERS:
            return True
        if username and username.lower() in Config.ALLOWED_USERS:
            return True
        return False

    # 3. If in public mode, allow everyone
    return True
