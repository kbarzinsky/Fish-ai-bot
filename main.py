import os
import requests
from datetime import datetime
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
import asyncio
import nest_asyncio

# Разрешаем вложенные event loops (для Railway)
nest_asyncio.apply()

try:
    from openai import OpenAI
    OPENAI_INSTALLED = True
except ImportError:
    OPENAI_INSTALLED = False

# --- ENV переменные ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENWEATHER_KEY = os.getenv("OPENWEATHER_KEY")
BOT_USERNAME = "@Recru1TFish_AI_bot"

print("BOT_TOKEN =", "FOUND" if BOT_TOKEN else "NOT FOUND")
print("OPENAI_API_KEY =", "FOUND" if OPENAI_API_KEY else "NOT FOUND")
print("OPENWEATHER_KEY =", "FOUND" if OPENWEATHER_KEY else "NOT FOUND")

if not BOT_TOKEN:
    print("Ошибка: BOT_TOKEN не задан! Бот не запустится.")

client = None
if OPENAI_API_KEY and OPENAI_INSTALLED:
    client = OpenAI(api_key=OPENAI_API_KEY)

SYSTEM_PROMPT = """
Ты профессиональный рыбак-эксперт.
Отвечай по погоде, давлению, ветру, времени клёва, снастях и приманках.
Давай рекомендации кратко, по делу и конкретно.
"""

WEATHER_URL = "http://api.openweathermap.org/data/2.5/weather"

def get_weather(city: str):
    if not OPENWEATHER_KEY:
        return None, "Погода недоступна — нет ключа OpenWeatherMap."
    try:
        r = requests.get(WEATHER_URL, params={"q": city, "appid": OPENWEATHER_KEY, "units": "metric"})
        data = r.json()
        temp = data["main"]["temp"]
        pressure = data["main"]["pressure"]
        wind = data["wind"]["speed"]
        description = data["weather"][0]["description"]
        weather_text = (f"{city}: {description}, "
                        f"Температура: {temp}°C, "
                        f"Давление: {pressure} hPa, "
                        f"Ветер: {wind} м/с")
        return data, weather_text
    except Exception as e:
        return None, f"Ошибка получения погоды: {e}"

def predict_bite_time(weather_data):
    if not weather_data:
        return "Время клёва неизвестно (нет данных о погоде)."
    temp = weather_data["main"]["temp"]
    pressure = weather_data["main"]["pressure"]

    hour = datetime.now().hour
    if 5 <= hour <= 9 or 17 <= hour <= 20:
        base = "активный клёв утром/вечером"
    else:
        base = "низкая активность"

    if pressure < 1000:
        base += ", давление низкое — рыба активнее"
    elif pressure > 1020:
        base += ", давление высокое — рыба менее активна"

    if temp < 5:
        base += ", вода холодная — осторожно с наживкой"
    elif temp > 25:
        base += ", вода тёплая — лучше лёгкие приманки"

    return base

async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    text = update.message.text.lower()
    if not ("/fish" in text or BOT_USERNAME in text):
        return

    parts = text.split(" ", 2)
    city = parts[1] if len(parts) > 1 else None
    fish_type = parts[2] if len(parts) > 2 else "рыба"

    weather_data, weather_info = get_weather(city) if city else (None, "Город не указан, погода недоступна.")
    bite_time = predict_bite_time(weather_data)

    prompt = f"{SYSTEM_PROMPT}\nПользователь написал: {update.message.text}\nПогода: {weather_info}\nВремя клёва: {bite_time}\nРыба: {fish_type}"

    if client:
        try:
            response = client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=[{"role": "user", "content": prompt}]
            )
            answer = response.choices[0].message.content
        except Exception as e:
            answer = f"Ошибка OpenAI: {e}\nПопробуй позже."
    else:
        answer = f"{weather_info}\n{bite_time}\nТестовый совет по {fish_type}"

    await update.message.reply_text(answer)

async def main():
    if not BOT_TOKEN:
        return

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT, handler))
    print("Бот запущен и ждёт сообщений...")
    await app.run_polling()

# --- Главное: исправлено, asyncio loop для Railway ---
if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
