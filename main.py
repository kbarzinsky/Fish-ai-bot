import os
import requests
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

# ---------- LOAD ENV ----------
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENWEATHER_KEY = os.getenv("OPENWEATHER_KEY")

if not BOT_TOKEN or not OPENWEATHER_KEY:
    raise RuntimeError("❌ Не заданы BOT_TOKEN или OPENWEATHER_KEY")

# ---------- UTILS ----------
def hpa_to_mm(hpa, city=""):
    city_altitude = {"курск": 200, "москва": 156}
    altitude = city_altitude.get(city.lower(), 0)
    return round((hpa - altitude * 0.12) * 0.75006)

def moon_phase():
    known_new_moon = datetime(2000, 1, 6, tzinfo=timezone.utc)
    days = (datetime.now(timezone.utc) - known_new_moon).days
    phase = days % 29.53

    if phase < 1.85:
        return "🌑 Новолуние"
    elif phase < 5.54:
        return "🌒 Растущий серп"
    elif phase < 9.23:
        return "🌓 Первая четверть"
    elif phase < 12.92:
        return "🌔 Растущая"
    elif phase < 16.61:
        return "🌕 Полнолуние"
    elif phase < 20.30:
        return "🌖 Убывающая"
    elif phase < 23.99:
        return "🌗 Последняя четверть"
    else:
        return "🌘 Убывающий серп"

def bite_rating(temp, pressure, wind, humidity, hour):
    score = 0
    if 735 <= pressure <= 741:
        score += 3
    if 1 <= wind <= 4:
        score += 2
    if humidity >= 60:
        score += 1
    if hour in range(5, 10) or hour in range(18, 22):
        score += 2
    return max(1, min(5, score))

def rating_emoji(r):
    return "🎣" * r + "⚪" * (5 - r)

def weather_text(main, rain, snow):
    base = {
        "clear": "☀️ Ясно",
        "clouds": "☁️ Облачно",
        "rain": "🌧 Дождь",
        "snow": "❄️ Снег",
        "drizzle": "🌦 Морось",
        "thunderstorm": "⛈ Гроза",
        "mist": "🌫 Туман",
    }.get(main, "🌈 Погода")

    if rain > 0:
        return f"🌧 Дождь {rain} мм"
    if snow > 0:
        return f"❄️ Снег {snow} мм"
    return base

# ---------- WEATHER ----------
def get_weather(city):
    r = requests.get(
        "https://api.openweathermap.org/data/2.5/weather",
        params={"q": city, "appid": OPENWEATHER_KEY, "units": "metric", "lang": "ru"},
        timeout=10
    )
    r.raise_for_status()
    d = r.json()

    return {
        "temp": round(d["main"]["temp"]),
        "humidity": d["main"]["humidity"],
        "wind": round(d["wind"]["speed"], 1),
        "pressure": hpa_to_mm(d["main"]["pressure"], city),
        "weather": d["weather"][0]["main"].lower(),
        "rain": d.get("rain", {}).get("1h", 0),
        "snow": d.get("snow", {}).get("1h", 0),
        "sunrise": d["sys"]["sunrise"],
        "sunset": d["sys"]["sunset"],
        "tz": d["timezone"]
    }

# ---------- HANDLERS ----------
async def station(update: Update, context: ContextTypes.DEFAULT_TYPE):
    city = "Курск"
    if context.args:
        city = " ".join(context.args)

    w = get_weather(city)
    tz = timezone(timedelta(seconds=w["tz"]))
    now = datetime.now(tz)

    bite = bite_rating(
        w["temp"], w["pressure"], w["wind"], w["humidity"], now.hour
    )

    text = (
        f"🎣 *Текущий прогноз*\n\n"
        f"*📍 Город:* {city}\n"
        f"*📅 День:* {now.strftime('%A %d.%m')}\n"
        f"*🕒 Сейчас:* {now.strftime('%H:%M')}\n\n"
        f"*🌦 Погода:* {weather_text(w['weather'], w['rain'], w['snow'])}\n"
        f"*🌡 Температура:* 🌞 день {w['temp']}°C / 🌙 ночь {w['temp'] - 4}°C\n"
        f"*💧 Влажность:* {w['humidity']}%\n"
        f"*💨 Ветер:* {w['wind']} м/с\n"
        f"*🧭 Давление:* {w['pressure']} мм\n"
        f"*🌅 Восход:* {datetime.fromtimestamp(w['sunrise'], tz).strftime('%H:%M')}\n"
        f"*🌇 Закат:* {datetime.fromtimestamp(w['sunset'], tz).strftime('%H:%M')}\n"
        f"*🌙 Луна:* {moon_phase()}\n"
        f"*🎯 Клёв:* {bite}/5 {rating_emoji(bite)}"
    )

    await update.message.reply_text(text, parse_mode="Markdown")

async def week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    city = "Курск"
    if context.args:
        city = " ".join(context.args)

    r = requests.get(
        "https://api.openweathermap.org/data/2.5/forecast",
        params={"q": city, "appid": OPENWEATHER_KEY, "units": "metric", "lang": "ru"},
        timeout=10
    )
    r.raise_for_status()
    data = r.json()

    tz = timezone(timedelta(seconds=data["city"]["timezone"]))
    days = {}

    for item in data["list"]:
        dt = datetime.fromtimestamp(item["dt"], tz)
        d = dt.date()
        days.setdefault(d, {
            "day": [], "night": [], "pressure": [],
            "humidity": [], "wind": [],
            "weather": [], "rain": [], "snow": []
        })

        if 6 <= dt.hour <= 18:
            days[d]["day"].append(item["main"]["temp"])
        else:
            days[d]["night"].append(item["main"]["temp"])

        days[d]["pressure"].append(item["main"]["pressure"])
        days[d]["humidity"].append(item["main"]["humidity"])
        days[d]["wind"].append(item["wind"]["speed"])
        days[d]["weather"].append(item["weather"][0]["main"].lower())
        days[d]["rain"].append(item.get("rain", {}).get("1h", 0))
        days[d]["snow"].append(item.get("snow", {}).get("1h", 0))

    out = f"📅 *Прогноз на 5 дней для {city}:*\n\n"

    for day, v in list(days.items())[:5]:
        temp_day = round(sum(v["day"]) / len(v["day"]))
        temp_night = round(sum(v["night"]) / len(v["night"]))
        pressure = hpa_to_mm(sum(v["pressure"]) / len(v["pressure"]), city)
        wind = round(sum(v["wind"]) / len(v["wind"]), 1)
        humidity = round(sum(v["humidity"]) / len(v["humidity"]))
        hour = 12

        bite = bite_rating(temp_day, pressure, wind, humidity, hour)

        out += (
            f"📅 *{day.strftime('%A %d.%m')}*\n\n"
            f"*🌦 Погода:* {weather_text(max(set(v['weather']), key=v['weather'].count), max(v['rain']), max(v['snow']))}\n"
            f"*🌡 Температура:* 🌞 {temp_day}°C / 🌙 {temp_night}°C\n"
            f"*💧 Влажность:* {humidity}%\n"
            f"*💨 Ветер:* {wind} м/с\n"
            f"*🧭 Давление:* {pressure} мм\n"
            f"*🌙 Луна:* {moon_phase()}\n"
            f"*🎯 Клёв:* {bite}/5 {rating_emoji(bite)}\n\n"
        )

    await update.message.reply_text(out, parse_mode="Markdown")

async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "📍 Текущий прогноз":
        await station(update, context)
    elif update.message.text == "📅 Прогноз на 5 дней":
        await week(update, context)

# ---------- MAIN ----------
def main():
    keyboard = ReplyKeyboardMarkup(
        [
            [KeyboardButton("📍 Текущий прогноз")],
            [KeyboardButton("📅 Прогноз на 5 дней")]
        ],
        resize_keyboard=True
    )

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("station", station))
    app.add_handler(CommandHandler("week", week))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, buttons))

    print("🚀 Бот запущен")
    app.run_polling()

if __name__ == "__main__":
    main()
        
