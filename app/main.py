import logging
import mimetypes
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
from app.telegram_utils import get_telegram_app, get_telethon_client
from tg_file_id.file_id import FileId
from telethon.tl.types import Document, DocumentAttributeVideo
import re
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

# Monkeypatch tg-file-id to support all version 4 sub-versions
def custom_parse_version(cls, decoded: bytearray):
    data, version = decoded[:-1], decoded[-1]
    if version == 4:
        data, sub_version = data[:-1], data[-1]
    else:
        sub_version = 0
    return data, version, sub_version

FileId._parse_version = classmethod(custom_parse_version)

# Initialize bot app
bot_app = get_telegram_app()

# Initialize Telethon client
telethon_client = get_telethon_client()

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
    
    logger.info("Starting Telethon client...")
    await telethon_client.start(bot_token=Config.BOT_TOKEN)
    logger.info("Telethon client started successfully.")
    
    yield  # FastAPI runs during this yield block
    
    logger.info("Shutting down: disconnecting Telethon client...")
    await telethon_client.disconnect()
    logger.info("Telethon client disconnected.")
    
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
async def stream_file(
    file_id: str, 
    file_name: str, 
    request: Request, 
    expires: int = None, 
    sig: str = None,
    size: int = None
):
    """
    Secure signed proxy streaming endpoint directly connected to Telegram MTProto.
    Supports instant seeking via byte Range Requests without local disk downloads.
    """
    # 0. Cryptographic security check
    if expires is None or sig is None or size is None:
        logger.warning(f"Rejected unsigned or incomplete stream request for file ID: {file_id}")
        raise HTTPException(status_code=403, detail="Access Denied: Unsigned or incomplete streaming link.")
        
    # Check link expiration status (valid for 3 hours 30 mins)
    current_time = int(time.time())
    if current_time > expires:
        logger.warning(f"Rejected expired stream request for file ID: {file_id} (expired {current_time - expires}s ago)")
        raise HTTPException(
            status_code=410, 
            detail="This streaming link has expired. Please generate a new link in the bot."
        )
        
    # Validate HMAC signature using bot token and size
    sig_payload = f"{file_id}:{expires}:{size}:{Config.BOT_TOKEN}"
    expected_sig = hashlib.sha256(sig_payload.encode()).hexdigest()[:16]
    if sig != expected_sig:
        logger.warning(f"Rejected invalid signature request for file ID: {file_id}")
        raise HTTPException(status_code=403, detail="Access Denied: Invalid cryptographic signature.")

    try:
        # 1. Resolve Bot API file ID to Telethon Document manually
        logger.info(f"Resolving Telethon media object for Bot API file ID: {file_id}")
        try:
            decoded = FileId.from_file_id(file_id)
            if not decoded:
                raise ValueError("Parsed result is empty.")
        except Exception as resolve_err:
            logger.error(f"Failed to resolve file ID: {resolve_err}")
            raise HTTPException(status_code=400, detail="Invalid file ID structure.")
            
        # Detect correct MIME type from file extension (critical for MKV subtitle tracks)
        content_type = mimetypes.guess_type(file_name)[0] or "application/octet-stream"

        media = Document(
            id=decoded.id,
            access_hash=decoded.access_hash,
            file_reference=bytes(decoded.file_reference),
            date=None,
            mime_type=content_type,
            size=size,
            dc_id=decoded.dc_id,
            thumbs=[],
            attributes=[
                DocumentAttributeVideo(
                    duration=0,
                    w=0,
                    h=0
                )
            ]
        )

        # 2. Parse Range Header
        start = 0
        end = size - 1
        is_range_request = False
        
        range_header = request.headers.get("range")
        if range_header:
            match = re.match(r"bytes=(\d+)-(\d+)?", range_header)
            if match:
                is_range_request = True
                start = int(match.group(1))
                if match.group(2):
                    end = int(match.group(2))
                    
        # Clamp ranges
        if start >= size:
            raise HTTPException(status_code=416, detail=f"Requested range not satisfiable (start {start} >= size {size})")
        if end >= size:
            end = size - 1

        length_to_read = end - start + 1
        
        # 3. Telethon requires offsets to be multiples of 4 KB (4096 bytes)
        aligned_offset = (start // 4096) * 4096
        skip_bytes = start - aligned_offset
        
        logger.info(f"Stream request range: {start}-{end}/{size} (Range request: {is_range_request}). Aligned offset: {aligned_offset}, Skip: {skip_bytes} bytes.")

        # 4. Prepare response headers
        response_headers = {
            "Content-Type": content_type,
            "Accept-Ranges": "bytes",
            "Content-Disposition": f'inline; filename="{file_name}"',
        }
        
        status_code = 200
        if is_range_request:
            status_code = 206
            response_headers["Content-Range"] = f"bytes {start}-{end}/{size}"
            response_headers["Content-Length"] = str(length_to_read)
        else:
            response_headers["Content-Length"] = str(size)

        # 5. Dual-stream interleaved engine — 2 long-lived connections with stride-based interleaving
        async def stream_generator(start_offset: int, skip_initial_bytes: int, total_bytes_to_read: int):
            CHUNK_SIZE = 1024 * 1024  # 1MB per chunk read
            NUM_WORKERS = 2
            STRIDE = NUM_WORKERS * CHUNK_SIZE  # 2MB stride — each worker reads every other chunk
            QUEUE_SIZE = 15  # 15 chunks buffered per worker = 30MB total read-ahead

            # Each worker gets its own output queue
            queues = [asyncio.Queue(maxsize=QUEUE_SIZE) for _ in range(NUM_WORKERS)]

            async def download_worker(worker_id):
                """Long-lived download stream. Uses stride to interleave with other workers."""
                worker_offset = start_offset + worker_id * CHUNK_SIZE
                try:
                    async for chunk in telethon_client.iter_download(
                        media,
                        offset=worker_offset,
                        request_size=CHUNK_SIZE,
                        stride=STRIDE,
                        file_size=size
                    ):
                        if not chunk:
                            break
                        await queues[worker_id].put(chunk)
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    logger.error(f"Download worker {worker_id} error: {e}")
                finally:
                    await queues[worker_id].put(None)  # End sentinel

            # Launch 2 persistent download streams
            workers = [asyncio.create_task(download_worker(i)) for i in range(NUM_WORKERS)]

            bytes_sent = 0
            skip_remaining = skip_initial_bytes

            try:
                finished = False
                while not finished:
                    # Alternate: read from Worker 0, then Worker 1, then Worker 0, ...
                    for wid in range(NUM_WORKERS):
                        chunk = await queues[wid].get()
                        if chunk is None:
                            finished = True
                            break

                        # Handle unaligned offset by skipping initial bytes
                        if skip_remaining > 0:
                            if len(chunk) <= skip_remaining:
                                skip_remaining -= len(chunk)
                                continue
                            chunk = chunk[skip_remaining:]
                            skip_remaining = 0

                        # Clamp to requested range
                        if bytes_sent + len(chunk) > total_bytes_to_read:
                            chunk = chunk[:(total_bytes_to_read - bytes_sent)]

                        if len(chunk) > 0:
                            # Yield in 64KB sub-chunks for smooth ASGI delivery
                            sub_size = 64 * 1024
                            for i in range(0, len(chunk), sub_size):
                                yield chunk[i:i + sub_size]
                            bytes_sent += len(chunk)

                        if bytes_sent >= total_bytes_to_read:
                            finished = True
                            break
            except Exception as stream_err:
                logger.error(f"Streaming interrupted: {stream_err}")
            finally:
                for w in workers:
                    w.cancel()
                logger.debug(f"Dual-stream finished. Sent {bytes_sent} bytes via {NUM_WORKERS} workers.")

        return StreamingResponse(
            stream_generator(aligned_offset, skip_bytes, length_to_read),
            status_code=status_code,
            headers=response_headers
        )
        
    except HTTPException as http_ex:
        raise http_ex
    except Exception as err:
        logger.error(f"Stream handler exception: {err}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal proxy server exception: {str(err)}")

if __name__ == "__main__":
    logger.info(f"Starting server on {Config.HOST}:{Config.PORT}...")
    uvicorn.run("app.main:app", host=Config.HOST, port=Config.PORT, reload=False)
