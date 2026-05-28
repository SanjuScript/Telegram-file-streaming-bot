import logging
import asyncio
from urllib.parse import quote
from telegram import Update
from telegram.ext import ContextTypes
from app.config import Config
from app.telegram_utils import is_user_allowed

logger = logging.getLogger(__name__)

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handler for /start command.
    """
    user = update.effective_user
    if not is_user_allowed(user.id, user.username):
        logger.warning(f"Unauthorized access attempt by User ID: {user.id}, Username: {user.username}")
        await update.message.reply_text("❌ Access Denied: You are not authorized to use this bot.")
        return

    welcome_text = (
        f"👋 Hello {user.first_name}!\n\n"
        "🎬 Welcome to **Telegram Stream Link Generator Bot**.\n\n"
        "Send me any video, audio, or document file, and I will generate secure, "
        "streamable links that you can play directly in VLC, MX Player, browsers, or other media players!\n\n"
        "💡 *Tip:* Send movies as files/documents to prevent compression."
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")

async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handler for /help command.
    """
    user = update.effective_user
    if not is_user_allowed(user.id, user.username):
        await update.message.reply_text("❌ Access Denied.")
        return

    help_text = (
        "📖 **How to Stream files:**\n\n"
        "1. Send a video, audio, or movie file directly to this bot.\n"
        "2. The bot will generate a streaming URL for you.\n"
        "3. Copy the secure stream URL.\n"
        "4. Paste it into your player of choice:\n"
        "   - **VLC**: Media -> Open Network Stream...\n"
        "   - **MX Player**: Network Stream\n"
        "   - **Browser**: Paste in address bar\n\n"
        "🛡️ *Note:* The secure proxy links hide your Telegram Bot Token. "
        "The direct links are faster but expose your bot token if shared with others."
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

# --- OWNER ADMIN COMMANDS ---

async def allow_all_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Owner command: Make the bot public.
    """
    user = update.effective_user
    if user.id != Config.OWNER_ID:
        logger.warning(f"Non-owner user {user.id} tried to call /allow_all")
        await update.message.reply_text("❌ Access Denied: This command is restricted to the bot owner.")
        return

    Config.set_private_mode(False)
    await update.message.reply_text(
        "🔓 **Public Mode Activated**\n\n"
        "Any Telegram user can now interact with the bot and generate streaming links.",
        parse_mode="Markdown"
    )

async def make_private_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Owner command: Make the bot private.
    """
    user = update.effective_user
    if user.id != Config.OWNER_ID:
        logger.warning(f"Non-owner user {user.id} tried to call /make_private")
        await update.message.reply_text("❌ Access Denied: This command is restricted to the bot owner.")
        return

    Config.set_private_mode(True)
    await update.message.reply_text(
        "🔒 **Private Mode Activated**\n\n"
        "Only the bot owner (and explicitly configured users) can now generate streaming links.",
        parse_mode="Markdown"
    )

async def status_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Owner command: Check bot status and stats.
    """
    user = update.effective_user
    if user.id != Config.OWNER_ID:
        logger.warning(f"Non-owner user {user.id} tried to call /status")
        await update.message.reply_text("❌ Access Denied.")
        return

    mode = "🔒 Private (Owner Only)" if Config.get_private_mode() else "🔓 Public (Everyone)"
    total_links = Config.get_total_links()
    
    status_text = (
        "ℹ️ **Bot Current Status:**\n\n"
        f"👤 **Owner ID:** `{Config.OWNER_ID}`\n"
        f"🛡️ **Access Mode:** {mode}\n"
        f"🎬 **Total Streams Generated:** `{total_links}`"
    )
    await update.message.reply_text(status_text, parse_mode="Markdown")

# --- MEDIA HANDLER ---

async def media_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handler for video, document, and audio files.
    """
    user = update.effective_user
    message = update.message
    
    if not is_user_allowed(user.id, user.username):
        logger.warning(f"Unauthorized media stream attempt by User ID: {user.id}, Username: {user.username}")
        await message.reply_text("❌ Access Denied: You are not authorized to use this bot.")
        return

    # Extract file details based on media type
    file_id = None
    file_name = None
    file_size_bytes = 0
    media_type = None

    if message.video:
        file_id = message.video.file_id
        file_name = message.video.file_name or "video.mp4"
        file_size_bytes = message.video.file_size
        media_type = "Video"
    elif message.document:
        file_id = message.document.file_id
        file_name = message.document.file_name or "document"
        file_size_bytes = message.document.file_size
        media_type = "Document"
    elif message.audio:
        file_id = message.audio.file_id
        file_name = message.audio.file_name or "audio.mp3"
        file_size_bytes = message.audio.file_size
        media_type = "Audio"
    else:
        await message.reply_text("⚠️ Unsupported media type. Please send a video, document, or audio file.")
        return

    # Trigger background download on the local Bot API server immediately so it starts caching
    logger.info(f"Preemptively triggering background download on local Bot API for ID: {file_id}")
    asyncio.create_task(context.bot.get_file(file_id, read_timeout=1800))

    file_size_mb = file_size_bytes / (1024 * 1024)
    logger.info(f"Generating stream link for {media_type}: '{file_name}' ({file_size_mb:.2f} MB) for User ID: {user.id}")

    # Create URL-safe file name
    safe_file_name = quote(file_name)
    
    # Construct Secure Proxy Stream URL
    secure_url = f"{Config.SERVER_URL}/stream/{file_id}/{safe_file_name}"
    
    # Warn user about files > 20MB if custom base URL is not set
    size_warning = ""
    if file_size_mb > 20.0 and not Config.TELEGRAM_BASE_URL:
        size_warning = (
            "\n⚠️ *Notice:* This file is larger than 20MB. Since a local Telegram Bot API Server is "
            "not configured in this bot, streaming might fail due to standard Telegram Bot API limitations. "
            "Please configure a local Bot API Server to stream files up to 2GB.\n"
        )

    # Increment statistics counter
    total_generated = Config.increment_links()

    # Respond to the requesting user with streaming URLs
    response_msg = (
        f"🎬 **Stream Links Generated!**\n\n"
        f"📁 **File:** `{file_name}`\n"
        f"📊 **Size:** `{file_size_mb:.2f} MB`\n"
        f"🏷️ **Type:** `{media_type}`\n"
        f"{size_warning}\n"
        f"🔒 **Secure Stream URL** (Recommended - token hidden):\n"
        f"`{secure_url}`\n\n"
        f"📱 *Tap/Click on the link box above to copy it to your clipboard.*"
    )
    
    await message.reply_text(response_msg, parse_mode="Markdown")

    # If another user makes the request, notify the owner
    if user.id != Config.OWNER_ID:
        username_formatted = f"@{user.username}" if user.username else "No Username"
        owner_notification = (
            f"🔔 **Stream Generated Alert**\n\n"
            f"👤 **Name:** {user.full_name}\n"
            f"🏷️ **Username:** {username_formatted}\n"
            f"🆔 **User ID:** `{user.id}`\n"
            f"📁 **File Name:** `{file_name}`\n"
            f"📊 **Size:** `{file_size_mb:.2f} MB`\n"
            f"⚡ **Total Stats Count:** `{total_generated}`\n\n"
            f"🔗 **Generated URL:**\n`{secure_url}`"
        )
        try:
            logger.info(f"Sending real-time admin alert to owner ({Config.OWNER_ID}) for request by {user.id}")
            await context.bot.send_message(
                chat_id=Config.OWNER_ID,
                text=owner_notification,
                parse_mode="Markdown"
            )
        except Exception as alert_err:
            logger.error(f"Failed to send real-time alert to owner: {alert_err}")
