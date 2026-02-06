import os
import requests
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENWEATHER_KEY = os.getenv("OPENWEATHER_KEY")

if not BOT_TOKEN or not OPENWEATHER_KEY:
    raise RuntimeError("❌ Не заданы переменные окружения")

# ---------- UTILS ----------

def format_time(ts):
    return datetime.fromtimestamp(ts).strftime("%H:%M")

def hpa_to_mm(hpa):
    return round(hpa * 0.75006)

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
        return round(data["current"].get("water_temp"))
    except:
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

    if water_temp:
        if 12 <= water_temp <= 22:
            score += 2
        else:
            score -= 1

    if hour in range(5, 10) or hour in range(18, 22):
        score += 2

    return max(1, min(5, score))

# ---------- HANDLER ----------

async def station(update: Update, context: ContextTypes.DEFAULT_TYPE):
    city = "Курск"
    if context.args:
        city = " ".join(context.args)

    w = get_weather(city)
    water = get_water_temp(w["lat"], w["lon"])
    hour = datetime.now().hour

    rating = bite_rating(
        w["temp"],
        w["pressure_mm"],
        w["wind"],
        w["humidity"],
        water,
        hour
    )

    text = (
        f"🎣 Рыбацкая метео-станция\n\n"
        f"📍 {city}\n"
        f"🕒 Сейчас: {datetime.now().strftime('%H:%M')}\n\n"
        f"🌡 Воздух: {w['temp']}°C\n"
        f"💧 Влажность: {w['humidity']}%\n"
        f"💨 Ветер: {w['wind']} м/с\n"
        f"🧭 Давление: {w['pressure_mm']} мм рт.ст.\n"
        f"🌅 Восход: {format_time(w['sunrise'])}\n"
        f"🌇 Закат: {format_time(w['sunset'])}\n"
    )

    if water:
        text += f"🌊 Температура воды: {water}°C\n"
    else:
        text += "🌊 Температура воды: нет данных\n"

    text += f"\n🐟 Клёв: {'⭐' * rating}"

    await update.message.reply_text(text)

# ---------- MAIN ----------

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("station", station))
    app.run_polling()

if __name__ == "__main__":
    main()
    
