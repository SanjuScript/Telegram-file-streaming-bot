import logging
import asyncio
import time
import hashlib
from urllib.parse import quote
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from app.config import Config
from app.telegram_utils import is_user_allowed

logger = logging.getLogger(__name__)

# --- ANIMATED STICKERS HELPER ---

async def send_animated_sticker(chat_id: int, category: str, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Fetch and send a random animated sticker from predefined sticker packs matching the category.
    Categories: 'success', 'error', 'confused'
    """
    import random
    packs = ["GreatMinds", "HotCherry", "ResistanceDog", "TofyCat", "LittleCorgi", "UtyaDuck"]
    random.shuffle(packs)
    
    category_emojis = {
        "success": ["🎉", "🥳", "👍", "❤️", "😎", "🔥", "👏", "⭐", "✅", "🙌"],
        "error": ["😢", "😭", "🤦", "😡", "❌", "👎", "🥺", "💔", "😞", "🩹"],
        "confused": ["🤔", "❓", "🤷", "🧐", "👀", "🔍", "💭", "❓"]
    }
    emojis = category_emojis.get(category, [])
    
    for pack_name in packs:
        try:
            sticker_set = await context.bot.get_sticker_set(name=pack_name)
            if not sticker_set or not sticker_set.stickers:
                continue
                
            # Filter for animated/video stickers that match category emojis
            matching = []
            for s in sticker_set.stickers:
                is_anim = getattr(s, "is_animated", False) or getattr(s, "is_video", False)
                if is_anim and s.emoji and any(e in s.emoji for e in emojis):
                    matching.append(s)
                    
            if matching:
                chosen = random.choice(matching)
                await context.bot.send_sticker(chat_id=chat_id, sticker=chosen.file_id)
                return
                
            # Fallback: send any animated/video sticker from the set
            animated = [s for s in sticker_set.stickers if getattr(s, "is_animated", False) or getattr(s, "is_video", False)]
            if animated:
                chosen = random.choice(animated)
                await context.bot.send_sticker(chat_id=chat_id, sticker=chosen.file_id)
                return
        except Exception:
            # Silence errors to try next pack
            continue

# --- BOT COMMANDS ---

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handler for /start command.
    """
    user = update.effective_user
    chat_id = update.effective_chat.id
    
    if not is_user_allowed(user.id, user.username):
        logger.warning(f"Unauthorized access attempt by User ID: {user.id}, Username: {user.username}")
        await send_animated_sticker(chat_id, "error", context)
        await update.message.reply_text("❌ Access Denied: You are not authorized to use this bot.")
        return

    await send_animated_sticker(chat_id, "success", context)
    
    welcome_text = (
        f"👋 Hello {user.first_name}!\n\n"
        "🎬 Welcome to **Telegram Stream Link Generator Bot**.\n\n"
        "Send me any video, audio, or document file, and I will generate secure, "
        "streamable links that you can play directly in VLC, MX Player, browsers, or other media players!\n\n"
        "⏰ *Notice:* Streaming links will expire after **3 hours and 30 minutes**.\n"
        "👨‍💻 *Developer:* **Sanju**"
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("👨‍💻 Contact Developer", url=f"tg://user?id={Config.OWNER_ID}")]
    ])
    
    await update.message.reply_text(welcome_text, parse_mode="Markdown", reply_markup=keyboard)

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
        "2. The bot will generate a secure streaming URL for you.\n"
        "3. Copy the secure stream URL.\n"
        "4. Paste it into your player of choice:\n"
        "   - **VLC**: Media -> Open Network Stream...\n"
        "   - **MX Player**: Network Stream\n"
        "   - **Browser**: Open direct URL\n\n"
        "⏰ *Expiration:* Links expire automatically after **3 hours 30 minutes**.\n"
        "🛡️ *Note:* Links are cryptographically signed and hide your Bot Token."
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

async def dev_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handler for /dev command (Developer info credits).
    """
    user = update.effective_user
    if not is_user_allowed(user.id, user.username):
        await update.message.reply_text("❌ Access Denied.")
        return

    dev_text = (
        "👨‍💻 **Developer Info**\n\n"
        "Developer: **Sanju**\n"
        "For feedback, issues, or requests, contact the developer directly."
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 Chat With Developer", url=f"tg://user?id={Config.OWNER_ID}")]
    ])
    
    await update.message.reply_text(dev_text, parse_mode="Markdown", reply_markup=keyboard)

# --- OWNER ADMIN COMMANDS ---

async def allowall_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Owner command: Make the bot public.
    """
    user = update.effective_user
    chat_id = update.effective_chat.id
    
    if user.id != Config.OWNER_ID:
        logger.warning(f"Non-owner user {user.id} tried to call /allowall")
        await update.message.reply_text("❌ Access Denied: This command is restricted to the bot developer.")
        return

    Config.set_private_mode(False)
    await send_animated_sticker(chat_id, "success", context)
    await update.message.reply_text(
        "🔓 **Public Mode Activated**\n\n"
        "Any Telegram user can now interact with the bot and generate streaming links.",
        parse_mode="Markdown"
    )

async def restricted_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Owner command: Make the bot private (restricted to developer & favorites).
    """
    user = update.effective_user
    chat_id = update.effective_chat.id
    
    if user.id != Config.OWNER_ID:
        logger.warning(f"Non-owner user {user.id} tried to call /restricted")
        await update.message.reply_text("❌ Access Denied: This command is restricted to the bot developer.")
        return

    Config.set_private_mode(True)
    await send_animated_sticker(chat_id, "success", context)
    await update.message.reply_text(
        "🔒 **Restricted Mode Activated**\n\n"
        "Only the developer and favorited users can now generate streaming links.",
        parse_mode="Markdown"
    )

async def fav_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Owner command: Add a User ID to favorites whitelist.
    """
    user = update.effective_user
    if user.id != Config.OWNER_ID:
        await update.message.reply_text("❌ Access Denied.")
        return

    if not context.args:
        await update.message.reply_text("⚠️ Usage: `/fav <user_id>` (e.g., `/fav 123456789`)", parse_mode="Markdown")
        return

    try:
        fav_id = int(context.args[0])
        success = Config.add_favorite(fav_id)
        if success:
            await update.message.reply_text(f"⭐ User `{fav_id}` added to **Favorites** whitelists successfully.", parse_mode="Markdown")
        else:
            await update.message.reply_text(f"ℹ️ User `{fav_id}` is already in the favorites list.", parse_mode="Markdown")
    except ValueError:
        await update.message.reply_text("❌ Invalid User ID. Must be a number.")

async def unfav_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Owner command: Remove a User ID from favorites whitelist.
    """
    user = update.effective_user
    if user.id != Config.OWNER_ID:
        await update.message.reply_text("❌ Access Denied.")
        return

    if not context.args:
        await update.message.reply_text("⚠️ Usage: `/unfav <user_id>` (e.g., `/unfav 123456789`)", parse_mode="Markdown")
        return

    try:
        fav_id = int(context.args[0])
        success = Config.remove_favorite(fav_id)
        if success:
            await update.message.reply_text(f"❌ User `{fav_id}` removed from **Favorites** whitelists.", parse_mode="Markdown")
        else:
            await update.message.reply_text(f"ℹ️ User `{fav_id}` was not found in the favorites list.", parse_mode="Markdown")
    except ValueError:
        await update.message.reply_text("❌ Invalid User ID. Must be a number.")

async def status_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Owner command: Check bot status, favorites list, and weekly usage analytics.
    """
    user = update.effective_user
    if user.id != Config.OWNER_ID:
        logger.warning(f"Non-owner user {user.id} tried to call /status")
        await update.message.reply_text("❌ Access Denied.")
        return

    mode = "🔒 Restricted (Dev & Favorites)" if Config.get_private_mode() else "🔓 Public (Everyone)"
    total_links = Config.get_total_links()
    
    # Get favorites whitelist details
    favs = Config.get_favorites()
    favs_str = ", ".join(f"`{fid}`" for fid in favs) if favs else "_None_"
    
    # Get analytics details
    analytics = Config.get_weekly_analytics()
    links_24h = analytics["links_24h"]
    links_7d = analytics["links_7d"]
    
    status_text = (
        "ℹ️ **Bot Current Status:**\n\n"
        f"👤 **Developer ID:** `{Config.OWNER_ID}`\n"
        f"🛡️ **Access Mode:** {mode}\n"
        f"⭐ **Favorites Count:** `{len(favs)}`\n"
        f"👥 **Favorites List:** {favs_str}\n\n"
        f"📊 **Usage Analytics:**\n"
        f"🎬 Last 24 Hours: `{links_24h}` files\n"
        f"🎬 Last 7 Days (Weekly): `{links_7d}` files\n"
        f"🎬 Cumulative Total: `{total_links}`"
    )
    await update.message.reply_text(status_text, parse_mode="Markdown")

# --- MEDIA HANDLER ---

async def media_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handler for video, document, and audio files.
    Calculates secure signatures with a 3.5h TTL and starts download.
    """
    user = update.effective_user
    message = update.message
    chat_id = update.effective_chat.id
    
    if not is_user_allowed(user.id, user.username):
        logger.warning(f"Unauthorized media stream attempt by User ID: {user.id}, Username: {user.username}")
        await send_animated_sticker(chat_id, "error", context)
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
        await send_animated_sticker(chat_id, "confused", context)
        await message.reply_text("⚠️ Unsupported media type. Please send a video, document, or audio file.")
        return

    file_size_mb = file_size_bytes / (1024 * 1024)
    logger.info(f"Generating stream link for {media_type}: '{file_name}' ({file_size_mb:.2f} MB) for User ID: {user.id}")

    # Trigger background download on the local Bot API server immediately so it starts caching
    logger.info(f"Preemptively triggering background download on local Bot API for ID: {file_id}")
    asyncio.create_task(context.bot.get_file(file_id, read_timeout=1800))

    # Send a Success animated sticker
    await send_animated_sticker(chat_id, "success", context)

    # Calculate expiration: 3 hours and 30 minutes (12600 seconds)
    expires = int(time.time()) + 12600
    
    # Generate cryptographic signature using the BOT_TOKEN as secret
    sig_payload = f"{file_id}:{expires}:{Config.BOT_TOKEN}"
    signature = hashlib.sha256(sig_payload.encode()).hexdigest()[:16]

    # Create URL-safe file name
    safe_file_name = quote(file_name)
    
    # Construct Secure Signed Proxy Stream URL
    secure_url = f"{Config.SERVER_URL}/stream/{file_id}/{safe_file_name}?expires={expires}&sig={signature}"
    
    # Warn user about files > 20MB if custom base URL is not set
    size_warning = ""
    if file_size_mb > 20.0 and not Config.TELEGRAM_BASE_URL:
        size_warning = (
            "\n⚠️ *Notice:* This file is larger than 20MB. Since a local Telegram Bot API Server is "
            "not configured in this bot, streaming might fail due to standard Telegram Bot API limitations.\n"
        )

    # Update stats and logs history
    total_generated = Config.increment_links()
    Config.add_request_log(user.id)

    # Respond to the requesting user with streaming details & inline buttons
    response_msg = (
        f"🎬 **Stream Links Generated!**\n\n"
        f"📁 **File:** `{file_name}`\n"
        f"📊 **Size:** `{file_size_mb:.2f} MB`\n"
        f"🏷️ **Type:** `{media_type}`\n"
        f"{size_warning}\n"
        f"🔒 **Secure Stream URL** (tap to copy):\n"
        f"`{secure_url}`\n\n"
        f"⏰ *Note: This link will expire after 3 hours and 30 minutes.*\n"
        f"👨‍💻 *Developer:* **Sanju**"
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎬 Open Stream", url=secure_url)],
        [InlineKeyboardButton("💬 Chat With Developer", url=f"tg://user?id={Config.OWNER_ID}")]
    ])
    
    await message.reply_text(response_msg, parse_mode="Markdown", reply_markup=keyboard)

    # If another user makes the request, notify the developer (owner)
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
