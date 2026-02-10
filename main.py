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
    raise RuntimeError("❌ Не заданы переменные окружения BOT_TOKEN или OPENWEATHER_KEY")

# ---------- UTILS ----------
def hpa_to_mm(hpa, city=""):
    city_altitude = {
        "курск": 200,
        "москва": 156,
    }
    altitude = city_altitude.get(city.lower(), 0)
    hpa_corrected = hpa - (altitude * 0.12)
    return round(hpa_corrected * 0.75006)

def get_moon_phase():
    known_new_moon = datetime(2000, 1, 6)
    days = (datetime.utcnow() - known_new_moon).days
    phase = (days % 29.53) / 29.53
    phases = ["🌑","🌒","🌓","🌔","🌕","🌖","🌗","🌘"]
    return phases[int(phase * 8) % 8]

def pressure_comment(pressure_mm):
    if 735 <= pressure_mm <= 741:
        return "🌟 Идеальное для клева"
    elif 742 <= pressure_mm <= 750:
        return "⚠ Немного высокое"
    elif pressure_mm < 735:
        return "⚠ Низкое"
    else:
        return "⚠ Слишком высокое"

def bite_rating(pressure, wind, humidity, rain, hour):
    score = 0

    if 735 <= pressure <= 741:
        score += 3
    elif 732 <= pressure < 735 or 741 < pressure <= 745:
        score += 2
    else:
        score -= 1

    if 1 <= wind <= 4:
        score += 2
    elif wind > 7:
        score -= 2

    if humidity >= 60:
        score += 1

    if rain > 0:
        score += 1  # лёгкий дождь часто плюс

    if hour in range(5, 10) or hour in range(18, 22):
        score += 2

    return max(1, min(5, score))

def rating_emoji(rating):
    return "🎣" * rating + "⚪" * (5 - rating)

# ---------- WEATHER ----------
def get_weather(city):
    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {"q": city, "appid": OPENWEATHER_KEY, "units": "metric", "lang": "ru"}
    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    data = r.json()

    pressure_mm = hpa_to_mm(data["main"]["pressure"], city)
    rain = data.get("rain", {}).get("1h", 0)
    snow = data.get("snow", {}).get("1h", 0)

    return {
        "temp": round(data["main"]["temp"]),
        "humidity": data["main"]["humidity"],
        "wind": round(data["wind"]["speed"], 1),
        "pressure_mm": pressure_mm,
        "sunrise": data["sys"]["sunrise"],
        "sunset": data["sys"]["sunset"],
        "rain": rain,
        "snow": snow,
        "timezone_offset": data.get("timezone", 0)
    }

# ---------- WEEK FORECAST ----------
def get_week_forecast_full(city):
    try:
        url = "https://api.openweathermap.org/data/2.5/forecast"
        params = {"q": city, "appid": OPENWEATHER_KEY, "units": "metric", "lang": "ru"}
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()

        tz_offset = timedelta(seconds=data["city"]["timezone"])
        moon = get_moon_phase()
        days = {}

        for item in data["list"]:
            dt = datetime.utcfromtimestamp(item["dt"]) + tz_offset
            day_key = dt.date()

            if day_key not in days:
                days[day_key] = {
                    "temp_day": [],
                    "temp_night": [],
                    "pressure": [],
                    "humidity": [],
                    "wind": [],
                    "rain": 0
                }

            hour = dt.hour
            if 6 <= hour <= 18:
                days[day_key]["temp_day"].append(item["main"]["temp"])
            else:
                days[day_key]["temp_night"].append(item["main"]["temp"])

            days[day_key]["pressure"].append(item["main"]["pressure"])
            days[day_key]["humidity"].append(item["main"]["humidity"])
            days[day_key]["wind"].append(item["wind"]["speed"])
            days[day_key]["rain"] += item.get("rain", {}).get("3h", 0)

        forecast_text = ""
        for i, (day, v) in enumerate(days.items()):
            if i >= 5:
                break

            temp_day = round(sum(v["temp_day"]) / len(v["temp_day"]))
            temp_night = round(sum(v["temp_night"]) / len(v["temp_night"]))
            pressure_avg = hpa_to_mm(sum(v["pressure"]) / len(v["pressure"]), city)
            humidity_avg = round(sum(v["humidity"]) / len(v["humidity"]))
            wind_avg = round(sum(v["wind"]) / len(v["wind"]), 1)
            rain = round(v["rain"], 1)

            rating = bite_rating(pressure_avg, wind_avg, humidity_avg, rain, 9)
            emoji = rating_emoji(rating)

            forecast_text += (
                f"*📅 {day.strftime('%a %d.%m')}*\n"
                f"🌡 День: {temp_day}°C, Ночь: {temp_night}°C\n"
                f"💧 Влажность: {humidity_avg}%\n"
                f"💨 Ветер: {wind_avg} м/с\n"
                f"🌧 Осадки: {rain} мм\n"
                f"🧭 Давление: {pressure_avg} мм рт.ст.\n"
                f"🌙 Луна: {moon}\n"
                f"🎯 Клев: {rating}/5 {emoji}\n\n"
            )

        return forecast_text

    except Exception as e:
        return f"❌ Ошибка прогноза: {e}"

# ---------- HANDLERS ----------
async def station(update: Update, context: ContextTypes.DEFAULT_TYPE):
    city = "Курск"
    if context.args:
        city = " ".join(context.args)

    try:
        w = get_weather(city)
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")
        return

    tz_offset = timedelta(seconds=w["timezone_offset"])
    local_now = datetime.utcnow() + tz_offset
    hour = local_now.hour

    rating = bite_rating(
        w["pressure_mm"], w["wind"], w["humidity"], w["rain"], hour
    )

    sunrise = (datetime.utcfromtimestamp(w["sunrise"]) + tz_offset).strftime("%H:%M")
    sunset = (datetime.utcfromtimestamp(w["sunset"]) + tz_offset).strftime("%H:%M")
    moon = get_moon_phase()

    text = (
        f"*🎣 Рыбацкая метео-станция*\n\n"
        f"*📍 Город:* {city}\n"
        f"*🕒 Сейчас:* {local_now.strftime('%H:%M')}\n\n"
        f"🌡 Воздух: {w['temp']}°C\n"
        f"💧 Влажность: {w['humidity']}%\n"
        f"💨 Ветер: {w['wind']} м/с\n"
        f"🌧 Осадки: {w['rain']} мм\n"
        f"🧭 Давление: {w['pressure_mm']} мм ({pressure_comment(w['pressure_mm'])})\n"
        f"🌅 Восход: {sunrise}\n"
        f"🌇 Закат: {sunset}\n\n"
        f"🌙 Луна: {moon}\n"
        f"🎯 Клев: {rating}/5 {rating_emoji(rating)}"
    )

    await update.message.reply_text(text, parse_mode="Markdown")

async def week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    city = "Курск"
    if context.args:
        city = " ".join(context.args)

    forecast = get_week_forecast_full(city)
    await update.message.reply_text(
        f"*Прогноз на 5 дней для {city}:*\n\n{forecast}",
        parse_mode="Markdown"
    )

# ---------- MAIN ----------
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("station", station))
    app.add_handler(CommandHandler("week", week))
    print("🎣 Рыбацкий бот запущен")
    app.run_polling()

if __name__ == "__main__":
    main()
    
