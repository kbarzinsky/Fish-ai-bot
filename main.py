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
    city_altitude = {"курск": 200, "москва": 156}
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

def weather_description(weather):
    """Возвращает погоду с эмодзи и русской расшифровкой"""
    main = weather["weather"][0]["main"].lower()
    desc = ""
    if main == "clear":
        desc = "☀ Ясно"
    elif main == "clouds":
        desc = "☁ Облачно"
    elif main == "rain":
        desc = f"🌧 Дождь {round(weather.get('rain', {}).get('1h', 0))} мм"
    elif main == "snow":
        desc = f"❄ Снег {round(weather.get('snow', {}).get('1h', 0))} мм"
    elif main == "drizzle":
        desc = f"🌦 Морось {round(weather.get('rain', {}).get('1h', 0))} мм"
    elif main == "thunderstorm":
        desc = "⛈ Гроза"
    else:
        desc = main.capitalize()
    return desc

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
        "temp_day": round(data["main"]["temp"]),
        "temp_night": round(data["main"]["temp"]),
        "humidity": data["main"]["humidity"],
        "wind": round(data["wind"]["speed"], 1),
        "pressure_mm": pressure_mm,
        "sunrise": data["sys"]["sunrise"],
        "sunset": data["sys"]["sunset"],
        "weather": data["weather"],
        "lat": data["coord"]["lat"],
        "lon": data["coord"]["lon"],
        "timezone_offset": data.get("timezone", 0)
    }

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

    tz = timedelta(seconds=w["timezone_offset"])
    local_now = datetime.utcnow() + tz
    hour = local_now.hour
    rating = bite_rating(w["temp"], w["pressure_mm"], w["wind"], w["humidity"], None, hour)
    emoji_rating_val = rating_emoji(rating)
    sunrise_time = (datetime.utcfromtimestamp(w["sunrise"]) + tz).strftime("%H:%M")
    sunset_time = (datetime.utcfromtimestamp(w["sunset"]) + tz).strftime("%H:%M")
    moon = get_moon_phase()
    weather_desc = weather_description(w)

    text = (
        f"*🎣 Рыбацкая метео-станция от Кирюхи*\n\n"
        f"*📍 Город:* {city}\n"
        f"*🕒 Сейчас:* {local_now.strftime('%H:%M')}\n\n"
        f"*🌤 Погода:* {weather_desc}\n"
        f"🌞 День: {w['temp_day']}°C  🌙 Ночь: {w['temp_night']}°C\n"
        f"💧 Влажность: {w['humidity']} %\n"
        f"💨 Ветер: {w['wind']} м/с\n"
        f"🧭 Давление: {w['pressure_mm']} мм рт.ст. ({pressure_comment(w['pressure_mm'])})\n"
        f"🌅 Восход: {sunrise_time}  🌇 Закат: {sunset_time}\n"
        f"🌙 Луна: {moon}\n"
        f"🎯 Клев: {rating}/5 {emoji_rating_val}"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    city = "Курск"
    if context.args:
        city = " ".join(context.args)

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
                days[day_key] = {"temp_day": [], "temp_night": [], "pressure": [], "humidity": [], "wind": [], "weather": []}
            hour = dt.hour
            if 6 <= hour <= 18:
                days[day_key]["temp_day"].append(item["main"]["temp"])
            else:
                days[day_key]["temp_night"].append(item["main"]["temp"])
            days[day_key]["pressure"].append(item["main"]["pressure"])
            days[day_key]["humidity"].append(item["main"]["humidity"])
            days[day_key]["wind"].append(item["wind"]["speed"])
            days[day_key]["weather"].append(item["weather"][0])

        forecast_text = ""
        count = 0
        for day, values in days.items():
            if count >= 5:
                break
            count += 1
            temp_day = round(sum(values["temp_day"]) / len(values["temp_day"])) if values["temp_day"] else None
            temp_night = round(sum(values["temp_night"]) / len(values["temp_night"])) if values["temp_night"] else None
            pressure_avg = round(hpa_to_mm(sum(values["pressure"]) / len(values["pressure"]), city))
            humidity_avg = round(sum(values["humidity"]) / len(values["humidity"]))
            wind_avg = round(sum(values["wind"]) / len(values["wind"]), 1)
            weather_desc = weather_description(values["weather"][0])
            rating = bite_rating(temp_day, pressure_avg, wind_avg, humidity_avg, None, 9)
            emoji_rating_val = rating_emoji(rating)

            forecast_text += (
                f"*📅 {day.strftime('%a %d.%m')}*\n"
                f"*🌤 Погода:* {weather_desc}\n"
                f"🌞 День: {temp_day}°C  🌙 Ночь: {temp_night}°C\n"
                f"💧 Влажность: {humidity_avg}%\n"
                f"💨 Ветер: {wind_avg} м/с\n"
                f"🧭 Давление: {pressure_avg} мм рт.ст. ({pressure_comment(pressure_avg)})\n"
                f"🌙 Луна: {moon}\n"
                f"🎯 Клев: {rating}/5 {emoji_rating_val}\n\n"
            )

    except Exception as e:
        forecast_text = f"❌ Не удалось получить прогноз: {e}"

    await update.message.reply_text(f"*Прогноз на 5 дней для {city}:*\n\n{forecast_text}", parse_mode="Markdown")

# ---------- MAIN ----------
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("station", station))
    app.add_handler(CommandHandler("week", week))
    print("Бот запущен! /station <город> /week <город>")
    app.run_polling()

if __name__ == "__main__":
    main()
