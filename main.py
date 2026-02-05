import os
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

try:
    from openai import OpenAI
    OPENAI_INSTALLED = True
except ImportError:
    OPENAI_INSTALLED = False

BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
BOT_USERNAME = "@fish_ai_bot"  # замените на username вашего бота

if not BOT_TOKEN:
    print("Ошибка: BOT_TOKEN не задан!")
if not OPENAI_API_KEY:
    print("Внимание: OPENAI_API_KEY не задан — бот будет отвечать тестовыми сообщениями")

if OPENAI_API_KEY and OPENAI_INSTALLED:
    client = OpenAI(api_key=OPENAI_API_KEY)
else:
    client = None

SYSTEM_PROMPT = """
Ты профессиональный рыбак-эксперт с большим опытом.
Ты умеешь:
- предсказывать клёв по погоде, давлению, ветру и сезону
- давать советы по снастям и приманкам
- объяснять, как лучше ловить рыбу в конкретных условиях
Отвечай кратко, по делу, как опытный рыбак рыбаку.
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
        answer = "Бот живой! Тестовый ответ без OpenAI."

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