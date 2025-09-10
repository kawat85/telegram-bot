import os
from flask import Flask, request
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters

# گرفتن توکن‌ها از Environment
TELEGRAM_TOKEN = os.environ.get("BOT_TOKEN")
OPENAI_KEY = os.environ.get("OPENAI_API_KEY")

# ساخت Flask app
app = Flask(__name__)

# ساخت Telegram Application
application = Application.builder().token(TELEGRAM_TOKEN).build()

# دستورات ربات
async def start(update: Update, context):
    await update.message.reply_text("سلام! ربات روشنه 🚀")

async def echo(update: Update, context):
    await update.message.reply_text(f"گفتی: {update.message.text}")

# هندلرها
application.add_handler(CommandHandler("start", start))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

# webhook route
@app.route(f"/{TELEGRAM_TOKEN}", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), application.bot)
    application.update_queue.put_nowait(update)
    return "ok", 200

@app.route("/")
def index():
    return "Bot is running!"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
