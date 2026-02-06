import os
import math
import requests
from datetime import datetime
import pytz

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# ================== ENV ==================
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")

if not BOT_TOKEN or not WEATHER_API_KEY:
    raise RuntimeError("❌ BOT_TOKEN или WEATHER_API_KEY не найден в .env")

# ================== CONST ==================
BASE_URL = "https://api.openweathermap.org/data/2.5"
FISHING_PRESSURE_GOOD = 738  # твоя подсказка 👍

# ================== UTILS ==================
def hpa_to_mmhg(hpa: float) -> int:
    # правильная конвертация
    return round(hpa * 0.75006)

def get_emoji(desc: str) -> str:
    desc = desc.lower()
    if "rain" in desc:
        return "🌧️"
    if "cloud" in desc:
        return "☁️"
    if "clear" in desc:
        return "☀️"
    if "snow" in desc:
        return "❄️"
    return "🌤️"

def fishing_pressure_status(mm: int) -> str:
    if mm == FISHING_PRESSURE_GOOD:
        return "🎣 ИДЕАЛЬНО для рыбалки"
    if mm < FISHING_PRESSURE_GOOD:
        return "🐟 Низкое — хищник активен"
    return "🐠 Высокое — рыба пассивна"

# ================== /station ==================
async def station(update: Update, context: ContextTypes.DEFAULT_TYPE):
    city = " ".join(context.args) if context.args else "Курск"

    url = f"{BASE_URL}/weather"
    params = {
        "q": city,
        "appid": WEATHER_API_KEY,
        "units": "metric",
        "lang": "ru"
    }

    r = requests.get(url, params=params).json()

    if r.get("cod") != 200:
        await update.message.reply_text("❌ Город не найден")
        return

    tz = pytz.timezone(f"Etc/GMT{-r['timezone']//3600:+d}")
    local_time = datetime.now(tz).strftime("%H:%M")

    pressure_mm = hpa_to_mmhg(r["main"]["pressure"])
    emoji = get_emoji(r["weather"][0]["description"])

    sunrise = datetime.fromtimestamp(r["sys"]["sunrise"], tz).strftime("%H:%M")
    sunset = datetime.fromtimestamp(r["sys"]["sunset"], tz).strftime("%H:%M")

    text = (
        f"🎣 Рыбацкая метеостанция от Кирюхи\n\n"
        f"📍 Город: *{r['name']}*\n"
        f"🕒 Местное время: {local_time}\n\n"
        f"{emoji} {r['weather'][0]['description'].capitalize()}\n"
        f"🌡 Температура: {round(r['main']['temp'])}°C\n"
        f"💧 Влажность: {r['main']['humidity']}%\n"
        f"🌬 Ветер: {r['wind']['speed']} м/с\n"
        f"🧭 Давление: {pressure_mm} мм рт. ст.\n"
        f"{fishing_pressure_status(pressure_mm)}\n\n"
        f"🌅 Восход: {sunrise}\n"
        f"🌇 Закат: {sunset}"
    )

    await update.message.reply_text(text, parse_mode="Markdown")

# ================== /week ==================
async def week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    city = " ".join(context.args) if context.args else "Курск"

    url = f"{BASE_URL}/forecast"
    params = {
        "q": city,
        "appid": WEATHER_API_KEY,
        "units": "metric",
        "lang": "ru"
    }

    r = requests.get(url, params=params).json()

    if r.get("cod") != "200":
        await update.message.reply_text("❌ Не удалось получить прогноз")
        return

    days = {}

    for item in r["list"]:
        date = item["dt_txt"].split(" ")[0]
        days.setdefault(date, []).append(item)

    text = f"📅 Прогноз на 5 дней — *{r['city']['name']}*\n\n"

    for date, items in list(days.items())[:5]:
        temps = [i["main"]["temp"] for i in items]
        hum = round(sum(i["main"]["humidity"] for i in items) / len(items))
        press = round(sum(hpa_to_mmhg(i["main"]["pressure"]) for i in items) / len(items))
        desc = items[0]["weather"][0]["description"]
        emoji = get_emoji(desc)

        text += (
            f"📆 *{date}*\n"
            f"{emoji} {desc.capitalize()}\n"
            f"🌡 {round(min(temps))}°C … {round(max(temps))}°C\n"
            f"💧 Влажность: {hum}%\n"
            f"🧭 Давление: {press} мм\n"
            f"{fishing_pressure_status(press)}\n\n"
        )

    await update.message.reply_text(text, parse_mode="Markdown")

# ================== MAIN ==================
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("station", station))
    app.add_handler(CommandHandler("week", week))

    print("✅ Бот запущен")
    app.run_polling()

if __name__ == "__main__":
    main()
    
