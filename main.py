import os
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

try:
    from openai import OpenAI
    OPENAI_INSTALLED = True
except ImportError:
    OPENAI_INSTALLED = False

# --- Токены через ENV ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
BOT_USERNAME = "@Recru1TFish_AI_bot"  # Замените на username вашего бота

if not BOT_TOKEN:
    print("Ошибка: BOT_TOKEN не задан!")
if not OPENAI_API_KEY:
    print("OpenAI ключ не задан — бот будет работать в тестовом режиме")

if OPENAI_API_KEY and OPENAI_INSTALLED:
    client = OpenAI(api_key=OPENAI_API_KEY)
else:
    client = None

SYSTEM_PROMPT = """
Ты профессиональный рыбак-эксперт.
Отвечай по погоде, давлению, клёву, снастях и приманках.
Кратко и по делу.
"""

async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    text = update.message.text.lower()
    if not ("/fish" in text or BOT_USERNAME in text):
        return

    if client:
        try:
            response = client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": update.message.text}
                ]
            )
            answer = response.choices[0].message.content
        except Exception as e:
            answer = f"Ошибка OpenAI: {e}\nПопробуй позже."
    else:
        answer = "Бот живой! Токен OpenAI не задан, ответ тестовый."

    await update.message.reply_text(answer)

async def main():
    if not BOT_TOKEN:
        print("BOT_TOKEN отсутствует, бот не будет запущен.")
        return

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT, handler))
    print("Бот запущен и ждёт сообщений...")
    await app.run_polling()

if name == "main":
    asyncio.run(main())