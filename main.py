import os
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

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

def get_moon_phase():
    phases = ["🌑","🌒","🌓","🌔","🌕","🌖","🌗","🌘"]
    return phases[(datetime.now().day * 8 // 30) % 8]

def pressure_comment(mm):
    if 735 <= mm <= 741:
        return "🌟 Идеальное для клёва"
    elif mm < 735:
        return "⚠ Низкое"
    else:
        return "⚠ Высокое"

def bite_rating(temp, pressure, wind, humidity, hour):
    score = 1
    if 735 <= pressure <= 741:
        score += 2
    if 1 <= wind <= 4:
        score += 1
    if humidity >= 60:
        score += 1
    if hour in range(5, 10) or hour in range(18, 22):
        score += 1
    return min(5, score)

def rating_emoji(r):
    return "🎣" * r + "⚪" * (5 - r)

def weather_text(main, rain, snow):
    emoji = {
        "clear":"☀️","clouds":"☁️","rain":"🌧","snow":"❄️",
        "drizzle":"🌦","thunderstorm":"⛈","mist":"🌫"
    }.get(main, "🌈")

    if rain > 0:
        return f"{emoji} Дождь, {rain} мм"
    if snow > 0:
        return f"{emoji} Снег, {snow} мм"

    return f"{emoji} { {'clear':'Ясно','clouds':'Облачно','mist':'Туман'}.get(main, main.capitalize()) }"

# ---------- API ----------
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
        "sunrise": d["sys"]["sunrise"],
        "sunset": d["sys"]["sunset"],
        "weather": d["weather"][0]["main"].lower(),
        "rain": d.get("rain", {}).get("1h", 0),
        "snow": d.get("snow", {}).get("1h", 0),
        "tz": d["timezone"]
    }

# ---------- /station ----------
async def station(update: Update, context: ContextTypes.DEFAULT_TYPE):
    city = "Курск" if not context.args else " ".join(context.args)
    w = get_weather(city)

    tz = timedelta(seconds=w["tz"])
    now = datetime.utcnow() + tz
    sunrise = (datetime.utcfromtimestamp(w["sunrise"]) + tz).strftime("%H:%M")
    sunset = (datetime.utcfromtimestamp(w["sunset"]) + tz).strftime("%H:%M")

    rating = bite_rating(w["temp"], w["pressure"], w["wind"], w["humidity"], now.hour)

    text = (
        f"🎣 *Рыбацкая метео-станция*\n\n"
        f"*📍 Город:* {city}\n"
        f"*🕒 Сейчас:* {now.strftime('%H:%M')}\n\n"
        f"*🌦 Погода:* {weather_text(w['weather'], w['rain'], w['snow'])}\n"
        f"*🌡 Температура:* 🌞 {w['temp']}°C / 🌙 {w['temp']}°C\n"
        f"*💧 Влажность:* {w['humidity']}%\n"
        f"*💨 Ветер:* {w['wind']} м/с\n"
        f"*🧭 Давление:* {w['pressure']} мм ({pressure_comment(w['pressure'])})\n"
        f"*🌅 Восход:* {sunrise}\n"
        f"*🌇 Закат:* {sunset}\n"
        f"*🌙 Луна:* {get_moon_phase()}\n"
        f"*🎯 Клёв:* {rating}/5 {rating_emoji(rating)}"
    )

    await update.message.reply_text(text, parse_mode="Markdown")

# ---------- /week ----------
async def week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    city = "Курск" if not context.args else " ".join(context.args)
    r = requests.get(
        "https://api.openweathermap.org/data/2.5/forecast",
        params={"q": city, "appid": OPENWEATHER_KEY, "units": "metric", "lang": "ru"},
        timeout=10
    )
    r.raise_for_status()
    data = r.json()

    tz = timedelta(seconds=data["city"]["timezone"])
    days = {}
    for i in data["list"]:
        dt = datetime.utcfromtimestamp(i["dt"]) + tz
        d = dt.date()
        days.setdefault(d, []).append(i)

    weekdays = ["Пн","Вт","Ср","Чт","Пт","Сб","Вс"]
    text = f"📅 *Прогноз на 5 дней для {city}:*\n\n"

    for d in list(days.keys())[:5]:
        items = days[d]
        temp_day = round(sum(i["main"]["temp"] for i in items) / len(items))
        pressure = hpa_to_mm(sum(i["main"]["pressure"] for i in items) / len(items), city)
        humidity = round(sum(i["main"]["humidity"] for i in items) / len(items))
        wind = round(sum(i["wind"]["speed"] for i in items) / len(items), 1)
        weather = items[0]["weather"][0]["main"].lower()
        rain = max(i.get("rain", {}).get("1h", 0) for i in items)
        snow = max(i.get("snow", {}).get("1h", 0) for i in items)
        rating = bite_rating(temp_day, pressure, wind, humidity, 9)

        text += (
            f"*📅 {weekdays[d.weekday()]} {d.strftime('%d.%m')}*\n"
            f"*🌦 Погода:* {weather_text(weather, rain, snow)}\n"
            f"*🌡 Температура:* 🌞 {temp_day}°C / 🌙 {temp_day}°C\n"
            f"*💧 Влажность:* {humidity}%\n"
            f"*💨 Ветер:* {wind} м/с\n"
            f"*🧭 Давление:* {pressure} мм ({pressure_comment(pressure)})\n"
            f"*🌙 Луна:* {get_moon_phase()}\n"
            f"*🎯 Клёв:* {rating}/5 {rating_emoji(rating)}\n\n"
        )

    await update.message.reply_text(text, parse_mode="Markdown")

# ---------- MAIN ----------
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("station", station))
    app.add_handler(CommandHandler("week", week))
    print("Бот запущен")
    app.run_polling()

if __name__ == "__main__":
    main()
