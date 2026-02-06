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
    """Конвертация давления hPa → мм рт. ст. с поправкой на высоту города"""
    city_altitude = {
        "курск": 200,
        "москва": 156,
        # добавляй другие города при необходимости
    }
    altitude = city_altitude.get(city.lower(), 0)
    hpa_corrected = hpa - (altitude * 0.12)
    return round(hpa_corrected * 0.75006)

def get_moon_phase():
    day = datetime.now().day
    phases = ["🌑","🌒","🌓","🌔","🌕","🌖","🌗","🌘"]
    return phases[(day * 8 // 30) % 8]

def pressure_comment(pressure_mm):
    if 735 <= pressure_mm <= 741:
        return "🌟 Идеальное для клева"
    elif 742 <= pressure_mm <= 750:
        return "⚠ Немного высокое"
    elif pressure_mm < 735:
        return "⚠ Низкое"
    else:
        return "⚠ Слишком высокое"

# ---------- WEATHER ----------
def get_weather(city):
    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {"q": city, "appid": OPENWEATHER_KEY, "units": "metric", "lang": "ru"}
    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    data = r.json()

    pressure_mm = hpa_to_mm(data["main"]["pressure"], city)

    return {
        "temp": round(data["main"]["temp"]),
        "humidity": data["main"]["humidity"],
        "wind": round(data["wind"]["speed"], 1),
        "pressure_mm": pressure_mm,
        "sunrise": data["sys"]["sunrise"],
        "sunset": data["sys"]["sunset"],
        "lat": data["coord"]["lat"],
        "lon": data["coord"]["lon"],
        "timezone_offset": data.get("timezone", 0)
    }

def get_water_temp(lat, lon):
    try:
        url = "https://api.openweathermap.org/data/2.5/onecall"
        params = {"lat": lat, "lon": lon, "appid": OPENWEATHER_KEY,
                  "units": "metric", "exclude": "minutely,hourly,alerts"}
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        return round(data["current"].get("temp"))
    except Exception:
        return None

def get_week_forecast(lat, lon, tz_offset):
    try:
        url = "https://api.openweathermap.org/data/2.5/onecall"
        params = {"lat": lat, "lon": lon, "appid": OPENWEATHER_KEY,
                  "units": "metric", "exclude": "minutely,hourly,alerts"}
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        forecast_text = ""
        for day in data["daily"]:
            date = datetime.utcfromtimestamp(day["dt"]) + tz_offset
            temp_day = round(day["temp"]["day"])
            temp_night = round(day["temp"]["night"])
            pressure_mm = hpa_to_mm(day["pressure"])
            forecast_text += f"{date.strftime('%a %d.%m')} — день {temp_day}°C, ночь {temp_night}°C, давление {pressure_mm} мм рт.ст.\n"
        return forecast_text
    except Exception:
        return "Не удалось получить недельный прогноз."

# ---------- BITE LOGIC ----------
def bite_rating(temp, pressure, wind, humidity, water_temp, hour):
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

# ---------- HANDLERS ----------
async def station(update: Update, context: ContextTypes.DEFAULT_TYPE):
    city = "Курск"
    if context.args:
        city = " ".join(context.args)

    try:
        w = get_weather(city)
    except Exception as e:
        await update.message.reply_text(f"Ошибка при получении погоды для {city}: {e}")
        return

    water = get_water_temp(w["lat"], w["lon"])
    tz_offset = timedelta(seconds=w["timezone_offset"])
    local_now = datetime.utcnow() + tz_offset
    hour = local_now.hour

    rating = bite_rating(w["temp"], w["pressure_mm"], w["wind"], w["humidity"], water, hour)
    emoji_rating = rating_emoji(rating)
    sunrise_time = (datetime.utcfromtimestamp(w["sunrise"]) + tz_offset).strftime("%H:%M")
    sunset_time = (datetime.utcfromtimestamp(w["sunset"]) + tz_offset).strftime("%H:%M")
    moon = get_moon_phase()

    text = (
        f"*🎣 Рыбацкая метео-станция от Кирюхи*\n\n"
        f"*📍 Город:* {city}\n"
        f"*🕒 Сейчас:* {local_now.strftime('%H:%M')}\n\n"
        f"*🌡 Воздух:* {w['temp']}°C\n"
        f"*💧 Влажность:* {w['humidity']} %\n"
        f"*💨 Ветер:* {w['wind']} м/с\n"
        f"*🧭 Давление:* {w['pressure_mm']} мм рт.ст. ({pressure_comment(w['pressure_mm'])})\n"
        f"*🌅 Восход:* {sunrise_time}\n"
        f"*🌇 Закат:* {sunset_time}\n"
    )

    if water is not None:
        text += f"*🌊 Температура воды:* {water}°C\n"

    text += f"\n*🌙 Луна:* {moon}\n"
    text += f"*🎯 Клев:* {rating}/5 {emoji_rating}"

    await update.message.reply_text(text, parse_mode="Markdown")

async def week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    city = "Курск"
    if context.args:
        city = " ".join(context.args)

    try:
        w = get_weather(city)
    except Exception as e:
        await update.message.reply_text(f"Ошибка при получении прогноза для {city}: {e}")
        return

    tz_offset = timedelta(seconds=w["timezone_offset"])
    forecast_text = get_week_forecast(w["lat"], w["lon"], tz_offset)
    await update.message.reply_text(f"*Прогноз на неделю для {city}:*\n\n{forecast_text}", parse_mode="Markdown")

# ---------- MAIN ----------
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("station", station))
    app.add_handler(CommandHandler("week", week))
    print("Бот запущен! Отправьте /station <город> или /week <город> в Telegram")
    app.run_polling()

if __name__ == "__main__":
    main()
    
