# ================= Import =================
import os
import json
import re
import docx
from collections import defaultdict
from flask import Flask, request

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

from openai import OpenAI

# ================= تنظیمات =================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "YOUR_OPENAI_API_KEY")
BOOKS_PATH = "books"   # مسیر پوشه کتاب‌ها در سرور

client = OpenAI(api_key=OPENAI_API_KEY)
user_scores = defaultdict(int)  # امتیاز هر کاربر

# ================= Flask برای وبهوک =================
app_flask = Flask(__name__)

# ================= استخراج متن از docx =================
def extract_text(path):
    doc = docx.Document(path)
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())

def load_books():
    if not os.path.exists(BOOKS_PATH):
        os.makedirs(BOOKS_PATH, exist_ok=True)
        print("[WARN] Books folder empty.")
        return {}
    books = {}
    for fname in os.listdir(BOOKS_PATH):
        if fname.endswith(".docx"):
            books[fname] = extract_text(os.path.join(BOOKS_PATH, fname))
    print("[INFO] Books loaded ✅")
    return books

books = load_books()

# ================= توابع OpenAI =================
def summarize_text(text: str) -> str:
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "یک خلاصه ساده و آموزشی از متن زیر بنویس:"},
            {"role": "user", "content": text}
        ],
        max_tokens=200
    )
    return resp.choices[0].message.content.strip()

def generate_quiz(text: str) -> dict:
    prompt = f"""
از متن زیر یک سوال تستی چهارگزینه‌ای طرح کن.
خروجی باید JSON معتبر باشد و فقط شامل question, options, answer.
فرمت:
{{
  "question": "متن سوال",
  "options": ["گزینه A", "گزینه B", "گزینه C", "گزینه D"],
  "answer": "گزینه صحیح"
}}

متن:
{text}
"""
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=300
    )

    raw_content = resp.choices[0].message.content
    raw_content = re.sub(r"```.*?```", "", raw_content, flags=re.DOTALL).strip()

    try:
        quiz = json.loads(raw_content)
        if len(quiz.get("options", [])) < 4:
            quiz["options"] = quiz.get("options", []) + ["A", "B", "C", "D"]
        if "answer" not in quiz:
            quiz["answer"] = quiz["options"][0]
    except Exception:
        quiz = {
            "question": raw_content.split("\n")[0],
            "options": ["A", "B", "C", "D"],
            "answer": "A"
        }
    return quiz

# ================= هندلرها =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🔍 جستجو", callback_data="search")],
        [InlineKeyboardButton("📝 تست", callback_data="quiz")],
        [InlineKeyboardButton("⭐ امتیاز من", callback_data="score")]
    ]
    await update.message.reply_text(
        "سلام 👋 یکی از گزینه‌های زیر رو انتخاب کن:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "search":
        await query.message.reply_text("عبارت مورد نظر رو بفرست:")
        context.user_data["mode"] = "search"

    elif query.data == "quiz":
        text = list(books.values())[0][:1000] if books else "متنی موجود نیست"
        q = generate_quiz(text)
        context.user_data["answer"] = q["answer"]

        keyboard = [[InlineKeyboardButton(opt, callback_data=opt)] for opt in q["options"]]
        await query.message.reply_text(
            f"❓ {q['question']}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif query.data == "score":
        score = user_scores[query.from_user.id]
        await query.message.reply_text(f"⭐ امتیاز فعلی شما: {score}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("mode") == "search":
        query = update.message.text.strip()
        results = []
        for name, text in books.items():
            for line in text.split("\n"):
                if query in line:
                    results.append(f"📖 {name}: {line}")

        if results:
            joined = "\n".join(results[:5])
            summary = summarize_text("\n".join(results[:5]))
            await update.message.reply_text(f"🔍 نتایج:\n{joined}\n\n📌 خلاصه:\n{summary}")
        else:
            await update.message.reply_text("چیزی پیدا نشد ❌")

        context.user_data["mode"] = None

async def answer_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    selected = query.data
    correct = context.user_data.get("answer")

    if not correct:
        return

    if selected == correct:
        user_scores[user_id] += 1
        await query.message.reply_text("✅ درست بود! +1 امتیاز")
    else:
        await query.message.reply_text(f"❌ اشتباه! پاسخ صحیح: {correct}")

    context.user_data["answer"] = None

# ================= پیکربندی ربات =================
application = Application.builder().token(TELEGRAM_TOKEN).build()
application.add_handler(CommandHandler("start", start))
application.add_handler(CallbackQueryHandler(button_handler, pattern="^(search|quiz|score)$"))
application.add_handler(CallbackQueryHandler(answer_handler))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# ================= Flask Webhook =================
@app_flask.route("/webhook", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), application.bot)
    application.update_queue.put_nowait(update)
    return "OK", 200

@app_flask.route("/")
def home():
    return "Bot is running ✅"

# ================= اجرای سرور =================
if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 8080))
    app_flask.run(host="0.0.0.0", port=PORT)
