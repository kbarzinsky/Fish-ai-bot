import os
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# ===== ENV =====
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENWEATHER_KEY = os.getenv("OPENWEATHER_KEY")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN not set")

if not OPENWEATHER_KEY:
    raise RuntimeError("OPENWEATHER_KEY not set")


# ===== WEATHER =====
def get_weather(city: str):
    url = (
        "https://api.openweathermap.org/data/2.5/weather"
        f"?q={city}&appid={OPENWEATHER_KEY}&units=metric&lang=ru"
    )
    r = requests.get(url, timeout=10)
    data = r.json()

    temp = data["main"]["temp"]
    pressure = data["main"]["pressure"]  # hPa
    wind = data["wind"]["speed"]
    desc = data["weather"][0]["description"]

    return temp, pressure, wind, desc


# ===== BITE LOGIC =====
def bite_rating(temp, pressure, wind):
    score = 0
    mm = pressure * 0.75006  # hPa -> mmHg

    if 745 <= mm <= 760:
        score += 2
    elif 735 <= mm <= 770:
        score += 1

    if wind <= 4:
        score += 2
    elif wind <= 7:
        score += 1

    if 10 <= temp <= 22:
        score += 1

    if score >= 4:
        return "🔥 Отличный клёв"
    elif score >= 2:
        return "🎣 Средний клёв"
    else:
        return "❌ Плохой клёв"


# ===== COMMANDS =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎣 Рыболовный бот готов!\n\n"
        "Команды:\n"
        "/weather <город> — погода\n"
        "/fish <город> — прогноз клёва"
    )


async def weather(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Пример:\n/weather Москва")
        return

    city = " ".join(context.args)

    try:
        temp, pressure, wind, desc = get_weather(city)
        text = (
            f"🌤 Погода в {city}\n"
            f"Описание: {desc}\n"
            f"🌡 Температура: {temp} °C\n"
            f"🌬 Ветер: {wind} м/с\n"
            f"🔽 Давление: {int(pressure * 0.75006)} мм"
        )
        await update.message.reply_text(text)
    except Exception:
        await update.message.reply_text("Ошибка получения погоды 😢")


async def fish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Пример:\n/fish Москва")
        return

    city = " ".join(context.args)

    try:
        temp, pressure, wind, desc = get_weather(city)
        rating = bite_rating(temp, pressure, wind)

        text = (
            f"🎣 Прогноз клёва — {city}\n\n"
            f"🌡 Температура: {temp} °C\n"
            f"🌬 Ветер: {wind} м/с\n"
            f"🔽 Давление: {int(pressure * 0.75006)} мм\n"
            f"🌥 Погода: {desc}\n\n"
            f"{rating}"
        )
        await update.message.reply_text(text)
    except Exception:
        await update.message.reply_text("Ошибка прогноза клёва 😢")


# ===== MAIN =====
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("weather", weather))
    app.add_handler(CommandHandler("fish", fish))
    app.run_polling()


if __name__ == "__main__":
    main()
