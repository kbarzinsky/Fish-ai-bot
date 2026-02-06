import os
import requests
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ---------- LOAD ENV ----------
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENWEATHER_KEY = os.getenv("OPENWEATHER_KEY")

if not BOT_TOKEN or not OPENWEATHER_KEY:
    raise RuntimeError("❌ Не заданы переменные окружения BOT_TOKEN или OPENWEATHER_KEY")

# ---------- UTILS ----------
def format_time(ts, tz):
    return datetime.fromtimestamp(ts, tz=tz).strftime("%H:%M")

def hpa_to_mm(hpa):
    return round(hpa * 0.75006)

def get_moon_phase():
    """Возвращает эмоджи фазы Луны"""
    day = datetime.now().day
    phases = ["🌑","🌒","🌓","🌔","🌕","🌖","🌗","🌘"]
    return phases[(day * 8 // 30) % 8]

# ---------- WEATHER ----------
def get_weather(city):
    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {
        "q": city,
        "appid": OPENWEATHER_KEY,
        "units": "metric",
        "lang": "ru"
    }

    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    data = r.json()

    return {
        "temp": round(data["main"]["temp"]),
        "humidity": data["main"]["humidity"],
        "wind": round(data["wind"]["speed"], 1),
        "pressure_mm": hpa_to_mm(data["main"]["pressure"]),
        "sunrise": data["sys"]["sunrise"],
        "sunset": data["sys"]["sunset"],
        "lat": data["coord"]["lat"],
        "lon": data["coord"]["lon"]
    }

def get_water_temp(lat, lon):
    try:
        url = "https://api.openweathermap.org/data/2.5/onecall"
        params = {
            "lat": lat,
            "lon": lon,
            "appid": OPENWEATHER_KEY,
            "units": "metric",
            "exclude": "minutely,hourly,alerts"
        }

        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        return round(data["current"].get("temp"))
    except Exception:
        return None

# ---------- BITE LOGIC ----------
def bite_rating(temp, pressure, wind, humidity, water_temp, hour):
    score = 0

    if 745 <= pressure <= 755:
        score += 3
    elif 740 <= pressure <= 760:
        score += 2
    else:
        score -= 1

    if 1 <= wind <= 4:
        score += 2
    elif wind > 7:
        score -= 2

    if humidity >= 60:
        score += 1

    if water_temp is not None:
        if 12 <= water_temp <= 22:
            score += 2
        else:
            score -= 1

    if hour in range(5, 10) or hour in range(18, 22):
        score += 2

    return max(1, min(5, score))

def rating_emoji(rating):
    return "🎣" * rating + "⚪" * (5 - rating)

# ---------- HANDLER ----------
async def station(update: Update, context: ContextTypes.DEFAULT_TYPE):
    city = "Курск"
    if context.args:
        city = " ".join(context.args)

    try:
        w = get_weather(city)
    except Exception as e:
        await update.message.reply_text(f"Ошибка при получении погоды: {e}")
        return

    water = get_water_temp(w["lat"], w["lon"])
    hour = datetime.now().hour
    rating = bite_rating(
        w["temp"], w["pressure_mm"], w["wind"], w["humidity"], water, hour
    )

    tz_kursk = timezone(timedelta(hours=3))
    sunrise_time = format_time(w['sunrise'], tz_kursk)
    sunset_time = format_time(w['sunset'], tz_kursk)
    moon = get_moon_phase()
    emoji_rating = rating_emoji(rating)

    text = (
        f"*🎣 Рыбацкая метео-станция*\n\n"
        f"*📍 Город:* {city}\n"
        f"*🕒 Сейчас:* {datetime.now(tz=tz_kursk).strftime('%H:%M')}\n\n"
        f"*🌡 Воздух:* {w['temp']}°C\n"
        f"*💧 Влажность:* {w['humidity']} %\n"
        f"*💨 Ветер:* {w['wind']} м/с\n"
        f"*🧭 Давление:* {w['pressure_mm']} мм рт.ст.\n"
        f"*🌅 Восход:* {sunrise_time}\n"
        f"*🌇 Закат:* {sunset_time}\n"
    )

    if water is not None:
        text += f"*🌊 Температура воды:* {water}°C\n"

    text += f"\n*🌙 Луна:* {moon}\n"
    text += f"*🎯 Клев:* {rating}/5 {emoji_rating}"

    await update.message.reply_text(text, parse_mode="Markdown")

# ---------- MAIN ----------
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("station", station))

    print("Бот запущен! Отправьте /station в Telegram")
    app.run_polling()

if __name__ == "__main__":
    main()
    
