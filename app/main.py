import logging
import os
import time
import hashlib
import asyncio
from contextlib import asynccontextmanager
import httpx
import uvicorn
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from telegram.ext import CommandHandler, MessageHandler, filters

from app.config import Config
from app.telegram_utils import get_telegram_app
from app.handlers import (
    start_handler, 
    help_handler, 
    media_handler, 
    allowall_handler, 
    restricted_handler, 
    fav_handler, 
    unfav_handler, 
    dev_handler, 
    status_handler
)

# Configure Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=getattr(logging, Config.LOG_LEVEL)
)
logger = logging.getLogger(__name__)

# Initialize bot app
bot_app = get_telegram_app()

# Register bot command handlers
bot_app.add_handler(CommandHandler("start", start_handler))
bot_app.add_handler(CommandHandler("help", help_handler))
bot_app.add_handler(CommandHandler("dev", dev_handler))
bot_app.add_handler(CommandHandler("allowall", allowall_handler))
bot_app.add_handler(CommandHandler("restricted", restricted_handler))
bot_app.add_handler(CommandHandler("fav", fav_handler))
bot_app.add_handler(CommandHandler("unfav", unfav_handler))
bot_app.add_handler(CommandHandler("status", status_handler))

# Register media handler for video, audio, and documents
bot_app.add_handler(MessageHandler(
    filters.VIDEO | filters.AUDIO | filters.Document.ALL, 
    media_handler
))

async def cleanup_old_files_loop():
    """
    Background loop that runs every 15 minutes to delete cached files
    older than 3.5 hours on the Xubuntu server disk to protect storage space.
    """
    # 3.5 hours = 12600 seconds
    max_age = 12600
    
    while True:
        try:
            # Check every 15 minutes
            await asyncio.sleep(900)
            
            if os.path.exists(Config.TELEGRAM_FILES_DIR):
                logger.info(f"Starting automatic disk cleanup sweep in: {Config.TELEGRAM_FILES_DIR}")
                now = time.time()
                deleted_count = 0
                deleted_bytes = 0
                
                # Walk through Bot API downloads directories
                for root_dir, dirs, files in os.walk(Config.TELEGRAM_FILES_DIR):
                    for file in files:
                        file_path = os.path.join(root_dir, file)
                        try:
                            mtime = os.path.getmtime(file_path)
                            age = now - mtime
                            if age > max_age:
                                file_size = os.path.getsize(file_path)
                                logger.info(f"Cleaning expired cached file: {file_path} (size: {file_size/(1024*1024):.2f} MB, age: {age/3600:.2f} hours)")
                                os.remove(file_path)
                                deleted_count += 1
                                deleted_bytes += file_size
                        except FileNotFoundError:
                            continue
                        except Exception as file_err:
                            logger.error(f"Error checking/deleting file {file_path}: {file_err}")
                
                if deleted_count > 0:
                    logger.info(f"Disk cleanup finished. Removed {deleted_count} files, freed {deleted_bytes/(1024*1024):.2f} MB of space.")
            else:
                logger.debug(f"Local files cache directory {Config.TELEGRAM_FILES_DIR} does not exist yet (no files downloaded).")
        except asyncio.CancelledError:
            logger.info("Disk cleanup background task was canceled.")
            break
        except Exception as loop_err:
            logger.error(f"Error in background cleanup loop: {loop_err}")
            await asyncio.sleep(60)  # Wait before retrying on error

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manage the lifecycle of the Telegram bot and background cleanup loops within the FastAPI event loop.
    """
    logger.info("Initializing Telegram bot application...")
    await bot_app.initialize()
    logger.info("Starting Telegram bot...")
    await bot_app.start()
    logger.info("Starting Telegram polling update loop...")
    await bot_app.updater.start_polling()
    
    # Start background file cleanup task
    cleanup_task = asyncio.create_task(cleanup_old_files_loop())
    logger.info("Disk space-saving auto-cleanup background task started.")
    
    yield  # FastAPI runs during this yield block
    
    logger.info("Shutting down: canceling background cleanup task...")
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass
        
    logger.info("Shutting down: stopping Telegram polling loop...")
    await bot_app.updater.stop()
    logger.info("Shutting down: stopping Telegram bot...")
    await bot_app.stop()
    logger.info("Shutting down: disposing Telegram bot resource allocations...")
    await bot_app.shutdown()

# Create FastAPI app with lifespan manager
app = FastAPI(
    title="Telegram Stream Link Generator Bot",
    description="A secure streaming proxy that generates playable range-aware URLs for Telegram media files.",
    version="1.1.0",
    lifespan=lifespan
)

@app.get("/")
async def root():
    """
    Root status endpoint.
    """
    return {
        "status": "online",
        "service": "Telegram Stream Link Generator Bot",
        "allowed_users_restricted": Config.get_private_mode()
    }

@app.get("/stream/{file_id}/{file_name}")
async def stream_file(file_id: str, file_name: str, request: Request, expires: int = None, sig: str = None):
    """
    Secure signed range-aware proxy streaming endpoint.
    Enforces expiration limits (3.5 hours) and validates SHA-256 links signatures.
    """
    # 0. Cryptographic security check
    if expires is None or sig is None:
        logger.warning(f"Rejected unsigned stream request for file ID: {file_id}")
        raise HTTPException(status_code=403, detail="Access Denied: Unsigned streaming link.")
        
    # Check link expiration status (valid for 3 hours 30 mins)
    current_time = int(time.time())
    if current_time > expires:
        logger.warning(f"Rejected expired stream request for file ID: {file_id} (expired {current_time - expires}s ago)")
        raise HTTPException(
            status_code=410, 
            detail="This streaming link has expired (valid for 3 hours and 30 minutes). Please generate a new link in the bot."
        )
        
    # Validate HMAC signature using bot token
    sig_payload = f"{file_id}:{expires}:{Config.BOT_TOKEN}"
    expected_sig = hashlib.sha256(sig_payload.encode()).hexdigest()[:16]
    if sig != expected_sig:
        logger.warning(f"Rejected invalid signature request for file ID: {file_id}")
        raise HTTPException(status_code=403, detail="Access Denied: Invalid cryptographic signature.")

    try:
        bot = bot_app.bot
        
        # 1. Retrieve the file path from Telegram Bot API (using 30-min read timeout for downloading)
        logger.info(f"Retrieving Telegram file metadata for ID: {file_id}")
        file_obj = await bot.get_file(file_id, read_timeout=1800)
        telegram_file_url = file_obj.file_path
        
        if not telegram_file_url:
            logger.error(f"Could not retrieve file path for ID: {file_id}")
            raise HTTPException(status_code=404, detail="File path not found on Telegram servers.")
            
        # 1.1 If it's a local file path (local mode)
        if not telegram_file_url.startswith(("http://", "https://")):
            if os.path.exists(telegram_file_url):
                logger.info(f"Streaming local file directly from disk: {telegram_file_url}")
                # FileResponse in FastAPI automatically handles HTTP Range requests and seeking!
                return FileResponse(
                    telegram_file_url,
                    media_type=None,  # Automatically detect mime type
                    filename=file_name
                )
            else:
                logger.error(f"Local file path does not exist inside bot container: {telegram_file_url}")
                raise HTTPException(
                    status_code=404, 
                    detail="Local file path not found. Please ensure the volume is mounted correctly at /var/lib/telegram-bot-api."
                )

        logger.debug(f"Resolved Telegram download URL: {telegram_file_url}")
        
        # 2. Extract and forward Range headers from client
        headers = {}
        if "range" in request.headers:
            headers["Range"] = request.headers["range"]
            logger.info(f"Forwarding Range Header: {headers['Range']}")
            
        # 3. Create HTTP client with no timeout for streaming large media files
        client = httpx.AsyncClient(timeout=None)
        req = client.build_request("GET", telegram_file_url, headers=headers)
        
        try:
            resp = await client.send(req, stream=True)
        except Exception as e:
            await client.aclose()
            logger.error(f"Failed to connect to Telegram file server: {e}")
            raise HTTPException(status_code=502, detail="Error communicating with Telegram storage servers.")
            
        status_code = resp.status_code
        logger.info(f"Telegram server responded with status code: {status_code}")
        
        # 4. Prepare response headers
        response_headers = {
            "Content-Type": resp.headers.get("Content-Type", "video/mp4"),
            "Accept-Ranges": "bytes",
        }
        
        # Forward relevant headers from Telegram response
        if "Content-Range" in resp.headers:
            response_headers["Content-Range"] = resp.headers["Content-Range"]
        if "Content-Length" in resp.headers:
            response_headers["Content-Length"] = resp.headers["Content-Length"]
        if "Content-Disposition" in resp.headers:
            response_headers["Content-Disposition"] = resp.headers["Content-Disposition"]
        else:
            response_headers["Content-Disposition"] = f'inline; filename="{file_name}"'

        # 5. Define asynchronous stream generator
        async def stream_generator():
            try:
                # 128KB buffer size is optimized for smooth network streaming
                async for chunk in resp.aiter_bytes(chunk_size=131072):
                    yield chunk
            except Exception as stream_err:
                logger.error(f"Network stream interrupted during file download: {stream_err}")
            finally:
                await resp.aclose()
                await client.aclose()
                logger.info("Closed streaming network client connections.")

        return StreamingResponse(
            stream_generator(),
            status_code=status_code,
            headers=response_headers
        )
        
    except Exception as err:
        logger.error(f"Stream handler error: {err}", exc_info=True)
        err_msg = str(err)
        if "File is too big" in err_msg:
            raise HTTPException(
                status_code=413, 
                detail="File is too big. Standard Telegram Bot API limit is 20MB. Please host a local Bot API Server to stream files up to 2GB."
            )
        raise HTTPException(status_code=500, detail=f"Internal proxy server exception: {err_msg}")

if __name__ == "__main__":
    logger.info(f"Starting server on {Config.HOST}:{Config.PORT}...")
    uvicorn.run("app.main:app", host=Config.HOST, port=Config.PORT, reload=False)
