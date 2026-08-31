import asyncio
import logging
from urllib.parse import urlparse

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from app.config import settings
from app.database import Database
from app.downloader import Downloader
from app.storage import Storage

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)
DB = Database(settings.database_path)
DL = Downloader(settings.download_dir, settings.temp_dir)
ST = Storage(settings.storage_endpoint, settings.storage_region, settings.storage_bucket, settings.storage_access_key, settings.storage_secret_key, settings.storage_presigned_ttl, settings.storage_public_base_url)
_QUEUE: asyncio.Queue[int] = asyncio.Queue()
_APP: Application | None = None


def valid_url(value: str) -> bool:
    try:
        p = urlparse(value)
        return p.scheme in {"http", "https"} and bool(p.netloc) and len(value) <= 4096
    except ValueError:
        return False


def size_text(n):
    if not n: return "?"
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024: return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}PB"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Send a supported media URL and I will show the available qualities.")


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    active = await DB.count_user_active_jobs(update.effective_user.id)
    await update.message.reply_text(f"Active jobs: {active}/{settings.max_active_jobs_per_user}")


async def receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = (update.message.text or "").strip()
    if not valid_url(url):
        return await update.message.reply_text("Please send a valid HTTP(S) URL.")
    if await DB.count_user_active_jobs(update.effective_user.id) >= settings.max_active_jobs_per_user:
        return await update.message.reply_text("You have reached the active-job limit. Try again later.")
    msg = await update.message.reply_text("🔎 Inspecting URL and available formats…")
    job_id = await DB.create_job(update.effective_user.id, update.effective_chat.id, url, "inspecting")
    await DB.update_job(job_id, message_id=msg.message_id)
    try:
        info = await asyncio.to_thread(DL.inspect, url)
        options = info["formats"]
        if not options:
            raise RuntimeError("No downloadable video formats")
        await DB.update_job(job_id, title=info["title"], status="pending")
        buttons = [[InlineKeyboardButton(f"{o.label} • {size_text(o.filesize)}", callback_data=f"fmt:{job_id}:{o.format_id}")] for o in options]
        await msg.edit_text(f"🎬 {info['title'][:800]}\n\nChoose a quality:", reply_markup=InlineKeyboardMarkup(buttons))
    except Exception as exc:
        log.exception("Extraction failed")
        await DB.update_job(job_id, status="failed", error=str(exc)[:1000])
        await msg.edit_text("❌ This URL could not be extracted or is unavailable.")


async def choose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    try:
        _, job_text, format_id = q.data.split(":", 2)
        job_id = int(job_text)
    except (ValueError, AttributeError):
        return await q.edit_message_text("Invalid selection.")
    job = await DB.get_job(job_id)
    if not job or job["user_id"] != q.from_user.id or job["status"] != "pending":
        return await q.edit_message_text("This selection has expired. Send the URL again.")
    if await DB.count_user_active_jobs(q.from_user.id) >= settings.max_active_jobs_per_user:
        return await q.edit_message_text("You have reached the active-job limit.")
    try:
        info = await asyncio.to_thread(DL.inspect, job["url"])
        option = next((f for f in info["formats"] if f.format_id == format_id), None)
        if option is None: raise RuntimeError("Selected format unavailable")
        await DB.update_job(job_id, status="queued", format_id=option.expression)
        await q.edit_message_text(f"⏳ Job #{job_id} queued…")
        await _QUEUE.put(job_id)
    except Exception as exc:
        await DB.update_job(job_id, status="failed", error=str(exc)[:1000])
        await q.edit_message_text("❌ The selected format is no longer available.")


async def run_job(job_id: int):
    job = await DB.get_job(job_id)
    if not job: return
    path = None
    try:
        await DB.update_job(job_id, status="downloading", attempts=job["attempts"] + 1)
        path = await asyncio.to_thread(DL.download, job["url"], job["format_id"], job_id)
        if path.stat().st_size > settings.max_file_size_mb * 1024 * 1024:
            raise RuntimeError("File exceeds configured maximum size")
        await DB.update_job(job_id, status="uploading", file_path=str(path))
        key = f"downloads/{job_id}/{path.name}"
        link = await asyncio.to_thread(ST.upload, path, key)
        await DB.update_job(job_id, status="completed", storage_key=key, download_url=link)
        await _APP.bot.send_message(job["chat_id"], f"✅ Job #{job_id} ready\n\n{link}")
    except Exception as exc:
        log.exception("Job %s failed", job_id)
        await DB.update_job(job_id, status="failed", error=str(exc)[:1000])
        await _APP.bot.send_message(job["chat_id"], f"❌ Job #{job_id} failed. Please try again with another URL or format.")
    finally:
        if path and path.exists():
            try: path.unlink()
            except OSError: log.warning("Could not remove %s", path)


async def worker():
    while True:
        job_id = await _QUEUE.get()
        try:
            await run_job(job_id)
        finally:
            _QUEUE.task_done()


async def post_init(app: Application):
    global _APP
    _APP = app
    await DB.init()
    await DB.recover_interrupted_jobs()
    for _ in range(max(1, settings.max_workers)):
        app.create_task(worker())
    for job in await DB.list_queued_jobs():
        await _QUEUE.put(job["id"])


def build_app() -> Application:
    app = Application.builder().token(settings.telegram_bot_token).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CallbackQueryHandler(choose, pattern=r"^fmt:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receive))
    return app


def main():
    build_app().run_polling(allowed_updates=Update.ALL_TYPES)
