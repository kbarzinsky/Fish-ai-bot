import os
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters
from openai import OpenAI

BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)

SYSTEM_PROMPT = """
Ты профессиональный рыбак-эксперт с большим практическим опытом.
Ты отлично разбираешься в:
- погоде и её влиянии на клёв
- атмосферном давлении и его изменениях
- сезонном поведении рыбы
- снастях, приманках и оснастках
- проводках и подаче приманки

При ответе:
1. Учитывай погоду, давление, ветер, сезон.
2. Объясняй, как это влияет на активность рыбы.
3. Даёшь конкретные советы: где, на что и как ловить.
4. Если данных не хватает — задай 1 уточняющий вопрос.
5. Отвечай кратко, по делу, без воды.
6. Общайся как опытный рыбак рыбаку.
"""

async def handler(update: Update, context):
    if not update.message or not update.message.text:
        return

    text = update.message.text.lower()

    # реагируем только на команду или упоминание
    if not ("/fish" in text or "@Recru1TFish_AI_bot" in text):
        return

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": update.message.text}
        ]
    )

    await update.message.reply_text(
        response.choices[0].message.content
    )

app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(MessageHandler(filters.TEXT, handler))
app.run_polling()