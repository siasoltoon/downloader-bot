import asyncio
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, CallbackQueryHandler, filters
from app.config import settings
from app.database import Database
from app.downloader import Downloader
from app.storage import Storage

DB=Database(settings.database_path)
DL=Downloader(settings.download_dir, settings.temp_dir)
ST=Storage(settings.storage_endpoint, settings.storage_region, settings.storage_bucket, settings.storage_access_key, settings.storage_secret_key, settings.storage_presigned_ttl)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Send a supported media URL to inspect available formats.")

async def receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url=(update.message.text or "").strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        return await update.message.reply_text("Please send a valid HTTP(S) URL.")
    msg=await update.message.reply_text("🔎 Inspecting URL and available formats…")
    try:
        info=await asyncio.to_thread(DL.inspect,url)
    except Exception as e:
        return await msg.edit_text(f"❌ Could not extract this URL.\n`{type(e).__name__}`", parse_mode="Markdown")
    context.user_data["pending_url"]=url
    context.user_data["formats"]={f.format_id:f for f in info["formats"]}
    buttons=[]
    for f in info["formats"]:
        label=f"{f.height}p" if f.height else f.label
        buttons.append([InlineKeyboardButton(label, callback_data=f"fmt:{f.format_id}")])
    if not buttons:
        return await msg.edit_text("No downloadable video formats were found.")
    await msg.edit_text(f"🎬 {info['title']}\n\nChoose a quality:", reply_markup=InlineKeyboardMarkup(buttons))

async def choose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    fid=q.data.split(":",1)[1]
    url=context.user_data.get("pending_url"); formats=context.user_data.get("formats",{})
    if not url or fid not in formats: return await q.edit_message_text("This selection has expired. Send the URL again.")
    job_id=await DB.create_job(q.from_user.id,url)
    await DB.update_job(job_id,status="downloading",format_id=fid)
    await q.edit_message_text("⏳ Download started…")
    try:
        path=await asyncio.to_thread(DL.download,url,fid,job_id)
        if path.stat().st_size > settings.max_file_size_mb*1024*1024:
            raise RuntimeError("File exceeds configured maximum size")
        key=f"downloads/{job_id}/{path.name}"
        link=await asyncio.to_thread(ST.upload,path,key)
        await DB.update_job(job_id,status="completed",file_path=str(path))
        await q.message.reply_text(f"✅ Ready\n\n{link}")
    except Exception as e:
        await DB.update_job(job_id,status="failed",error=str(e)[:1000])
        await q.message.reply_text(f"❌ Download failed: {type(e).__name__}")

async def post_init(app: Application):
    await DB.init()

def build_app():
    app=Application.builder().token(settings.telegram_bot_token).post_init(post_init).build()
    app.add_handler(CommandHandler("start",start))
    app.add_handler(CallbackQueryHandler(choose,pattern=r"^fmt:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,receive))
    return app

def main():
    build_app().run_polling(allowed_updates=Update.ALL_TYPES)
