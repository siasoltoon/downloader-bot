import asyncio
import logging
import time
from urllib.parse import urlsplit

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from telegram.request import HTTPXRequest

from app.config import settings
from app.database import Database
from app.downloader import Downloader
from app.storage import Storage
from app.validation import valid_url

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger(__name__)
DB = Database(settings.database_path)
DL = Downloader(settings.download_dir, settings.temp_dir)
ST = Storage(
    settings.storage_endpoint,
    settings.storage_region,
    settings.storage_bucket,
    settings.storage_access_key,
    settings.storage_secret_key,
    settings.storage_presigned_ttl,
    settings.storage_public_base_url,
)
_QUEUE: asyncio.Queue[int] = asyncio.Queue()
_APP: Application | None = None
_WORKERS: list[asyncio.Task] = []


def size_text(n):
    if not n:
        return "?"
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}PB"


def safe_host(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "unknown").lower()
    except ValueError:
        return "invalid"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    log.info("telegram:command start user=%s chat=%s", update.effective_user.id, update.effective_chat.id)
    await update.message.reply_text("Send a supported media URL and I will show the available qualities.")


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    active = await DB.count_user_active_jobs(update.effective_user.id)
    log.info("telegram:command status user=%s active_jobs=%s", update.effective_user.id, active)
    await update.message.reply_text(f"Active jobs: {active}/{settings.max_active_jobs_per_user}")


async def receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = (update.message.text or "").strip()
    host = safe_host(url)
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    log.info("job:received user=%s chat=%s host=%s", user_id, chat_id, host)
    if not valid_url(url):
        log.warning("job:rejected user=%s host=%s reason=invalid_url", user_id, host)
        return await update.message.reply_text("Please send a valid HTTP(S) URL.")
    active = await DB.count_user_active_jobs(user_id)
    if active >= settings.max_active_jobs_per_user:
        log.warning("job:rejected user=%s host=%s reason=active_limit active=%s", user_id, host, active)
        return await update.message.reply_text("You have reached the active-job limit. Try again later.")
    msg = await update.message.reply_text("🔎 Inspecting URL and available formats…")
    job_id = await DB.create_job(user_id, chat_id, url, "inspecting")
    await DB.update_job(job_id, message_id=msg.message_id)
    started = time.monotonic()
    log.info("job=%s stage=inspect:start host=%s", job_id, host)
    try:
        info = await asyncio.to_thread(DL.inspect, url)
        options = info["formats"]
        log.info(
            "job=%s stage=inspect:success extractor=%s formats=%s duration=%s elapsed=%.2fs",
            job_id,
            info.get("extractor") or "unknown",
            len(options),
            info.get("duration"),
            time.monotonic() - started,
        )
        if not options:
            raise RuntimeError("No downloadable video formats")
        await DB.update_job(job_id, title=info["title"], status="pending")
        buttons = [
            [
                InlineKeyboardButton(
                    f"{o.label} • {size_text(o.filesize)}",
                    callback_data=f"fmt:{job_id}:{o.format_id}",
                )
            ]
            for o in options
        ]
        await msg.edit_text(
            f"🎬 {info['title'][:800]}\n\nChoose a quality:",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        log.info("job=%s stage=formats:presented count=%s", job_id, len(options))
    except Exception as exc:
        log.exception("job=%s stage=inspect:failed type=%s", job_id, type(exc).__name__)
        await DB.update_job(job_id, status="failed", error=f"{type(exc).__name__}: {str(exc)[:500]}")
        await msg.edit_text("❌ This URL could not be extracted or is unavailable.")


async def choose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    try:
        _, job_text, format_id = q.data.split(":", 2)
        job_id = int(job_text)
    except (ValueError, AttributeError):
        log.warning("job:selection_invalid user=%s", q.from_user.id)
        return await q.edit_message_text("Invalid selection.")
    log.info("job=%s stage=selection:received user=%s format=%s", job_id, q.from_user.id, format_id)
    job = await DB.get_job(job_id)
    if not job or job["user_id"] != q.from_user.id or job["status"] != "pending":
        log.warning("job=%s stage=selection:rejected user=%s reason=invalid_or_expired", job_id, q.from_user.id)
        return await q.edit_message_text("This selection has expired. Send the URL again.")
    if await DB.count_user_active_jobs(q.from_user.id) >= settings.max_active_jobs_per_user:
        log.warning("job=%s stage=selection:rejected reason=active_limit", job_id)
        return await q.edit_message_text("You have reached the active-job limit.")
    started = time.monotonic()
    try:
        log.info("job=%s stage=reinspect:start", job_id)
        info = await asyncio.to_thread(DL.inspect, job["url"])
        option = next((f for f in info["formats"] if f.format_id == format_id), None)
        if option is None:
            raise RuntimeError("Selected format unavailable")
        await DB.update_job(job_id, status="queued", format_id=option.expression)
        await q.edit_message_text(f"⏳ Job #{job_id} queued…")
        await _QUEUE.put(job_id)
        log.info("job=%s stage=queued format=%s elapsed=%.2fs", job_id, option.expression, time.monotonic() - started)
    except Exception as exc:
        log.exception("job=%s stage=selection:failed type=%s", job_id, type(exc).__name__)
        await DB.update_job(job_id, status="failed", error=f"Selection failed: {type(exc).__name__}: {str(exc)[:500]}")
        await q.edit_message_text("❌ The selected format is no longer available.")


async def run_job(job_id: int):
    job = await DB.get_job(job_id)
    if not job:
        log.error("job=%s stage=run:missing", job_id)
        return
    path = None
    started = time.monotonic()
    host = safe_host(job["url"])
    log.info("job=%s stage=run:start host=%s", job_id, host)
    try:
        attempts = job["attempts"] + 1
        await DB.update_job(job_id, status="downloading", attempts=attempts)
        log.info("job=%s stage=download:start attempt=%s format=%s", job_id, attempts, job["format_id"])
        path = await asyncio.to_thread(DL.download, job["url"], job["format_id"], job_id)
        file_size = path.stat().st_size
        log.info("job=%s stage=download:success file=%s size=%d elapsed=%.2fs", job_id, path.name, file_size, time.monotonic() - started)
        if file_size > settings.max_file_size_mb * 1024 * 1024:
            raise RuntimeError(f"File exceeds configured maximum size ({settings.max_file_size_mb} MB)")
        await DB.update_job(job_id, status="uploading", file_path=str(path))
        key = f"downloads/{job_id}/{path.name}"
        log.info("job=%s stage=upload:start key=%s size=%d", job_id, key, file_size)
        link = await asyncio.to_thread(ST.upload, path, key)
        log.info("job=%s stage=upload:success link_type=%s", job_id, "public" if settings.storage_public_base_url else "presigned")
        await DB.update_job(job_id, status="completed", storage_key=key, download_url=link)
        await _APP.bot.send_message(job["chat_id"], f"✅ Job #{job_id} ready\n\n{link}")
        log.info("job=%s stage=complete success elapsed=%.2fs", job_id, time.monotonic() - started)
    except Exception as exc:
        log.exception("job=%s stage=run:failed host=%s type=%s elapsed=%.2fs", job_id, host, type(exc).__name__, time.monotonic() - started)
        await DB.update_job(job_id, status="failed", error=f"{type(exc).__name__}: {str(exc)[:500]}")
        try:
            await _APP.bot.send_message(job["chat_id"], f"❌ Job #{job_id} failed. Check the server log for details.")
        except Exception:
            log.exception("job=%s stage=error_notification:failed", job_id)
    finally:
        if path and path.exists():
            try:
                path.unlink()
                log.info("job=%s stage=cleanup:success file=%s", job_id, path.name)
            except OSError:
                log.exception("job=%s stage=cleanup:failed file=%s", job_id, path.name)


async def worker(worker_id: int):
    log.info("worker=%s started", worker_id)
    while True:
        job_id = await _QUEUE.get()
        log.info("worker=%s picked job=%s", worker_id, job_id)
        try:
            await run_job(job_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("worker=%s unexpected job=%s failure", worker_id, job_id)
        finally:
            _QUEUE.task_done()


async def post_init(app: Application):
    global _APP, _WORKERS
    _APP = app
    log.info("application:init database=%s workers=%s", settings.database_path, settings.max_workers)
    await DB.init()
    await DB.recover_interrupted_jobs()
    for _ in range(max(1, settings.max_workers)):
        worker_id = len(_WORKERS) + 1
        _WORKERS.append(asyncio.create_task(worker(worker_id), name=f"download-worker-{worker_id}"))
    queued = await DB.list_queued_jobs()
    for job in queued:
        await _QUEUE.put(job["id"])
    log.info("application:init complete recovered_queued_jobs=%s workers=%s", len(queued), len(_WORKERS))


def build_app() -> Application:
    bot_request = HTTPXRequest(
        connect_timeout=15.0,
        read_timeout=30.0,
        write_timeout=30.0,
        pool_timeout=10.0,
        connection_pool_size=16,
    )
    updates_request = HTTPXRequest(
        connect_timeout=15.0,
        read_timeout=30.0,
        write_timeout=30.0,
        pool_timeout=10.0,
        connection_pool_size=16,
    )
    return (
        Application.builder()
        .token(settings.telegram_bot_token)
        .request(bot_request)
        .get_updates_request(updates_request)
        .post_init(post_init)
        .post_stop(post_stop)
        .build()
    )


async def post_stop(app: Application):
    log.info("application:stop cancelling_workers=%s", len(_WORKERS))
    for task in _WORKERS:
        if not task.done():
            task.cancel()
    if _WORKERS:
        await asyncio.gather(*_WORKERS, return_exceptions=True)
    _WORKERS.clear()
    log.info("application:stop complete")


def main():
    app = build_app()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CallbackQueryHandler(choose, pattern=r"^fmt:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receive))
    app.run_polling(allowed_updates=Update.ALL_TYPES)
