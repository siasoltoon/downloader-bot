import asyncio
import os
from urllib.parse import urlparse

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application, CallbackQueryHandler, CommandHandler, ContextTypes,
    MessageHandler, filters,
)

from app.config import settings
from app.database import Database
from app.downloader import Downloader
from app.storage import Storage

DB = Database(settings.database_path)
DL = Downloader(settings.download_dir, settings.temp_dir)
ST = Storage(
    settings.storage_endpoint, settings.storage_region, settings.storage_bucket,
    settings.storage_access_key, settings.storage_secret_key, settings.storage_presigned_ttl,
)
JOB_LIMIT = asyncio.Semaphore(max(1, settings.max_workers))


def valid_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
    except ValueError:
        return False


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Send a supported media URL. I will inspect it and show the available video qualities."
    )


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    active = await DB.count_user_active_jobs(update.effective_user.id)
    await update.message.reply_text(f"Active jobs: {active}/{settings.max_active_jobs_per_user}")


async def receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = (update.message.text or "").strip()
    if not valid_url(url):
        return await update.message.reply_text("Please send a valid HTTP(S) URL.")

    active = await DB.count_user_active_jobs(update.effective_user.id)
    if active >= settings.max_active_jobs_per_user:
        return await update.message.reply_text("You have reached the active-job limit. Try again later.")

    pending_id = await DB.create_job(update.effective_user.id, update.effective_chat.id, url)
    msg = await update.message.reply_text("🔎 Inspecting URL and available formats…")
    await DB.update_job(pending_id, message_id=msg.message_id, status="inspecting")

    try:
        info = await asyncio.to_thread(DL.inspect, url)
    except Exception as exc:
        await DB.update_job(pending_id, status="failed", error=str(exc)[:1000])
        return await msg.edit_text(f"❌ Could not extract this URL.\n{type(exc).__name__}")

    await DB.update_job(pending_id, title=info["title"], status="pending")
    buttons = []
    for option in info["formats"]:
        suffix = " + audio" if not option.has_audio else ""
        buttons.append([InlineKeyboardButton(
            f"{option.label}{suffix}", callback_data=f"fmt:{pending_id}:{option.format_id}"
        )])
    if not buttons:
        await DB.update_job(pending_id, status="failed", error="No video formats")
        return await msg.edit_text("No downloadable video formats were found.")

    title = info["title"][:800]
    await msg.edit_text(f"🎬 {title}\n\nChoose a quality:", reply_markup=InlineKeyboardMarkup(buttons))


async def choose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        _, job_text, format_id = query.data.split(":", 2)
        job_id = int(job_text)
    except (ValueError, AttributeError):
        return await query.edit_message_text("Invalid selection.")

    job = await DB.get_job(job_id)
    if not job or job["user_id"] != query.from_user.id or job["status"] != "pending":
        return await query.edit_message_text("This selection has expired. Send the URL again.")

    try:
        info = await asyncio.to_thread(DL.inspect, job["url"])
        option = next((f for f in info["formats"] if f.format_id == format_id), None)
        if option is None:
            raise RuntimeError("Selected format is no longer available")
    except Exception as exc:
        await DB.update_job(job_id, status="failed", error=str(exc)[:1000])
        return await query.edit_message_text("❌ The selected format is no longer available.")

    await DB.update_job(job_id, status="queued", format_id=option.expression)
    await query.edit_message_text("⏳ Job queued…")
    asyncio.create_task(run_job(job_id))


async def run_job(job_id: int):
    job = await DB.get_job(job_id)
    if not job:
        return
    try:
        await DB.update_job(job_id, status="downloading", attempts=job["attempts"] + 1)
        async with JOB_LIMIT:
            path = await asyncio.to_thread(DL.download, job["url"], job["format_id"], job_id)
            if path.stat().st_size > settings.max_file_size_mb * 1024 * 1024:
                raise RuntimeError("File exceeds configured maximum size")
            await DB.update_job(job_id, status="uploading", file_path=str(path))
            key = f"downloads/{job_id}/{path.name}"
            link = await asyncio.to_thread(ST.upload, path, key)
            await DB.update_job(job_id, status="completed", storage_key=key, download_url=link)
            await send_result(job["chat_id"], link)
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
    except Exception as exc:
        await DB.update_job(job_id, status="failed", error=str(exc)[:1000])
        await send_result(job["chat_id"], f"❌ Download failed: {type(exc).__name__}")


async def send_result(chat_id: int, text: str):
    # Stored application instance is injected by post_init.
    if _APP is not None:
        await _APP.bot.send_message(chat_id=chat_id, text=text)


_APP: Application | None = None


async def post_init(app: Application):
    global _APP
    _APP = app
    await DB.init()
    # Jobs interrupted by a process restart are made visible as failed rather than left hanging.
    for job in await DB.list_active_jobs():
        await DB.update_job(job["id"], status="failed", error="Interrupted by application restart")


def build_app() -> Application:
    app = Application.builder().token(settings.telegram_bot_token).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CallbackQueryHandler(choose, pattern=r"^fmt:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receive))
    return app


def main():
    build_app().run_polling(allowed_updates=Update.ALL_TYPES)
