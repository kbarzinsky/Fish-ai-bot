import os
import requests
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import openai

# ---------- LOAD ENV ----------
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENWEATHER_KEY = os.getenv("OPENWEATHER_KEY")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")

if not BOT_TOKEN or not OPENWEATHER_KEY:
    raise RuntimeError("❌ Не заданы переменные окружения BOT_TOKEN или OPENWEATHER_KEY")
if not OPENAI_KEY:
    raise RuntimeError("❌ Не заданы переменные окружения OPENAI_API_KEY")

openai.api_key = OPENAI_KEY
# Если нужен прокси:
# openai.proxy = "http://user:password@host:port"

# ---------- UTILS ----------
def hpa_to_mm(hpa, city=""):
    city_altitude = {"курск": 200, "москва": 156}
    altitude = city_altitude.get(city.lower(), 0)
    hpa_corrected = hpa - (altitude * 0.12)
    return round(hpa_corrected * 0.75006)

def get_moon_phase():
    known_new_moon = datetime(2000, 1, 6, tzinfo=timezone.utc)
    days = (datetime.now(timezone.utc) - known_new_moon).days
    phases = ["🌑","🌒","🌓","🌔","🌕","🌖","🌗","🌘"]
    return phases[(days * 8 // 29) % 8]

def pressure_comment(pressure_mm):
    if 735 <= pressure_mm <= 741:
        return "🌟 Идеальное для клева"
    elif 742 <= pressure_mm <= 750:
        return "⚠ Немного высокое"
    elif pressure_mm < 735:
        return "⚠ Низкое"
    else:
        return "⚠ Слишком высокое"

def bite_rating(temp, pressure, wind, humidity, hour):
    score = 0
    if 735 <= pressure <= 741: score += 3
    elif 732 <= pressure < 735 or 741 < pressure <= 745: score += 2
    else: score -= 1
    if 1 <= wind <= 4: score += 2
    elif wind > 7: score -= 2
    if humidity >= 60: score += 1
    if hour in range(5, 10) or hour in range(18, 22): score += 2
    return max(1, min(5, score))

def rating_emoji(rating):
    return "🎣" * rating + "⚪" * (5 - rating)

def weather_icon(weather_main):
    icons = {
        "Clear": "☀️",
        "Clouds": "☁️",
        "Rain": "🌧️",
        "Drizzle": "🌦️",
        "Thunderstorm": "⛈️",
        "Snow": "❄️",
        "Mist": "🌫️",
        "Fog": "🌫️"
    }
    return icons.get(weather_main, "")

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
        "sunrise": datetime.fromtimestamp(data["sys"]["sunrise"], tz=timezone.utc),
        "sunset": datetime.fromtimestamp(data["sys"]["sunset"], tz=timezone.utc),
        "lat": data["coord"]["lat"],
        "lon": data["coord"]["lon"],
        "weather": data["weather"][0]["main"],
        "timezone_offset": timedelta(seconds=data.get("timezone", 0))
    }

def get_week_forecast(city):
    url = "https://api.openweathermap.org/data/2.5/forecast"
    params = {"q": city, "appid": OPENWEATHER_KEY, "units": "metric", "lang": "ru"}
    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    data = r.json()
    tz_offset = timedelta(seconds=data["city"]["timezone"])
    moon = get_moon_phase()
    days = {}

    for item in data["list"]:
        dt = datetime.fromtimestamp(item["dt"], tz=timezone.utc) + tz_offset
        day_key = dt.date()
        if day_key not in days:
            days[day_key] = {"temp_day": [], "temp_night": [], "pressure": [], "humidity": [], "wind": [], "weather": []}
        hour = dt.hour
        if 6 <= hour <= 18: days[day_key]["temp_day"].append(item["main"]["temp"])
        else: days[day_key]["temp_night"].append(item["main"]["temp"])
        days[day_key]["pressure"].append(item["main"]["pressure"])
        days[day_key]["humidity"].append(item["main"]["humidity"])
        days[day_key]["wind"].append(item["wind"]["speed"])
        days[day_key]["weather"].append(item["weather"][0]["main"])

    ru_weekdays = ["Пн","Вт","Ср","Чт","Пт","Сб","Вс"]
    forecast_text = ""
    count = 0

    for day, values in days.items():
        if count >= 5: break
        count += 1
        temp_day = round(sum(values["temp_day"])/len(values["temp_day"])) if values["temp_day"] else None
        temp_night = round(sum(values["temp_night"])/len(values["temp_night"])) if values["temp_night"] else None
        pressure_avg = round(hpa_to_mm(sum(values["pressure"])/len(values["pressure"]), city))
        humidity_avg = round(sum(values["humidity"])/len(values["humidity"]))
        wind_avg = round(sum(values["wind"])/len(values["wind"]),1)
        weather_main = max(set(values["weather"]), key=values["weather"].count)
        rating = bite_rating(temp_day, pressure_avg, wind_avg, humidity_avg, 9)
        emoji = rating_emoji(rating)
        weekday_ru = ru_weekdays[day.weekday()]

        forecast_text += (
            f"*📅 {weekday_ru} {day.strftime('%d.%m')}* {weather_icon(weather_main)}\n"
            f"🌡 День: {temp_day}°C, Ночь: {temp_night}°C\n"
            f"💧 Влажность: {humidity_avg}%\n"
            f"💨 Ветер: {wind_avg} м/с\n"
            f"🧭 Давление: {pressure_avg} мм рт.ст. ({pressure_comment(pressure_avg)})\n"
            f"🌙 Луна: {moon}\n"
            f"🎯 Клев: {rating}/5 {emoji}\n\n"
        )
    return forecast_text

# ---------- HANDLERS ----------
async def station(update: Update, context: ContextTypes.DEFAULT_TYPE):
    city = "Курск" if not context.args else " ".join(context.args)
    try:
        w = get_weather(city)
    except Exception as e:
        await update.message.reply_text(f"Ошибка при получении погоды: {e}")
        return
    local_now = datetime.now(timezone.utc) + w["timezone_offset"]
    hour = local_now.hour
    rating = bite_rating(w["temp"], w["pressure_mm"], w["wind"], w["humidity"], hour)
    emoji_rating_val = rating_emoji(rating)
    text = (
        f"*🎣 Рыбацкая метео-станция*\n\n"
        f"*📍 Город:* {city}\n"
        f"*🕒 Сейчас:* {local_now.strftime('%H:%M')}\n"
        f"*🌡 Воздух:* {w['temp']}°C\n"
        f"*💧 Влажность:* {w['humidity']}%\n"
        f"*💨 Ветер:* {w['wind']} м/с\n"
        f"*🧭 Давление:* {w['pressure_mm']} мм рт.ст. ({pressure_comment(w['pressure_mm'])})\n"
        f"*🌅 Восход:* {(w['sunrise'] + w['timezone_offset']).strftime('%H:%M')}\n"
        f"*🌇 Закат:* {(w['sunset'] + w['timezone_offset']).strftime('%H:%M')}\n"
        f"*🌙 Луна:* {get_moon_phase()}\n"
        f"*🎯 Клев:* {rating}/5 {emoji_rating_val}\n"
        f"*Погода:* {weather_icon(w['weather'])} {w['weather']}"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    city = "Курск" if not context.args else " ".join(context.args)
    try:
        forecast_text = get_week_forecast(city)
    except Exception as e:
        await update.message.reply_text(f"Ошибка при получении прогноза: {e}")
        return
    await update.message.reply_text(f"*Прогноз на 5 дней для {city}:*\n\n{forecast_text}", parse_mode="Markdown")

async def expert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    question = " ".join(context.args)
    if not question:
        await update.message.reply_text("❌ Задай вопрос после команды /expert")
        return
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[{"role":"user","content":question}],
            timeout=20
        )
        answer = response['choices'][0]['message']['content']
        await update.message.reply_text(f"🤖 Expert:\n{answer}")
    except openai.error.OpenAIError as e:
        await update.message.reply_text(f"Ошибка GPT: {e}")

# ---------- MAIN ----------
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("station", station))
    app.add_handler(CommandHandler("week", week))
    app.add_handler(CommandHandler("expert", expert))
    print("Бот запущен! /station <город> /week <город> /expert <вопрос>")
    app.run_polling()

if __name__ == "__main__":
    main()
        
