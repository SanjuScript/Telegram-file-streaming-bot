import logging
from contextlib import asynccontextmanager
import httpx
import uvicorn
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse
from telegram.ext import CommandHandler, MessageHandler, filters

from app.config import Config
from app.telegram_utils import get_telegram_app
from app.handlers import start_handler, help_handler, media_handler, allow_all_handler, make_private_handler, status_handler

# Configure Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=getattr(logging, Config.LOG_LEVEL)
)
logger = logging.getLogger(__name__)

# Initialize bot app
bot_app = get_telegram_app()

# Register bot handlers
bot_app.add_handler(CommandHandler("start", start_handler))
bot_app.add_handler(CommandHandler("help", help_handler))
bot_app.add_handler(CommandHandler("allow_all", allow_all_handler))
bot_app.add_handler(CommandHandler("make_private", make_private_handler))
bot_app.add_handler(CommandHandler("status", status_handler))
# Register media handler for video, audio, and documents
bot_app.add_handler(MessageHandler(
    filters.VIDEO | filters.AUDIO | filters.Document.ALL, 
    media_handler
))

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manage the lifecycle of the Telegram bot within the FastAPI event loop.
    """
    logger.info("Initializing Telegram bot application...")
    await bot_app.initialize()
    logger.info("Starting Telegram bot...")
    await bot_app.start()
    logger.info("Starting Telegram polling update loop...")
    await bot_app.updater.start_polling()
    
    yield  # FastAPI runs during this yield block
    
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
    version="1.0.0",
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
        "allowed_users_restricted": len(Config.ALLOWED_USERS) > 0
    }

@app.get("/stream/{file_id}/{file_name}")
async def stream_file(file_id: str, file_name: str, request: Request):
    """
    Secure range-aware proxy streaming endpoint.
    Resolves the Telegram file_id to a path and streams it.
    Exposing this endpoint hides the bot token from downstream media players.
    """
    try:
        bot = bot_app.bot
        
        # 1. Retrieve the file path from Telegram Bot API
        # Increase read_timeout to 1800s (30 mins) to allow local Bot API to download large files
        logger.info(f"Retrieving Telegram file metadata for ID: {file_id}")
        file_obj = await bot.get_file(file_id, read_timeout=1800)
        telegram_file_url = file_obj.file_path
        
        if not telegram_file_url:
            logger.error(f"Could not retrieve file path for ID: {file_id}")
            raise HTTPException(status_code=404, detail="File path not found on Telegram servers.")
            
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
