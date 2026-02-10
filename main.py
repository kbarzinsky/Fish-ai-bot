import os
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import openai

# ---------- LOAD ENV ----------
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENWEATHER_KEY = os.getenv("OPENWEATHER_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY

if not BOT_TOKEN or not OPENWEATHER_KEY or not OPENAI_API_KEY:
    raise RuntimeError("❌ Не заданы BOT_TOKEN, OPENWEATHER_KEY или OPENAI_API_KEY")

# ---------- UTILS ----------
def hpa_to_mm(hpa, city=""):
    city_altitude = {"курск": 200, "москва": 156}
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
        return "🌟 Идеальное для клёва"
    elif 742 <= pressure_mm <= 750:
        return "⚠ Немного высокое"
    elif pressure_mm < 735:
        return "⚠ Низкое"
    else:
        return "⚠ Слишком высокое"

def weather_icon(weather_main):
    return {
        "Clear": "☀️",
        "Clouds": "☁️",
        "Rain": "🌧",
        "Drizzle": "🌦",
        "Thunderstorm": "⛈",
        "Snow": "❄️",
        "Mist": "🌫",
        "Fog": "🌫",
        "Haze": "🌫",
    }.get(weather_main, "🌡")

def ru_weekday(date_obj):
    return ["Пн","Вт","Ср","Чт","Пт","Сб","Вс"][date_obj.weekday()]

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
        score += 1
    if hour in range(5, 10) or hour in range(18, 22):
        score += 2
    return max(1, min(5, score))

def rating_emoji(r):
    return "🎣" * r + "⚪" * (5 - r)

# ---------- WEATHER ----------
def get_weather(city):
    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {"q": city, "appid": OPENWEATHER_KEY, "units": "metric", "lang": "ru"}
    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    data = r.json()
    return {
        "temp": round(data["main"]["temp"]),
        "humidity": data["main"]["humidity"],
        "wind": round(data["wind"]["speed"], 1),
        "pressure_mm": hpa_to_mm(data["main"]["pressure"], city),
        "sunrise": data["sys"]["sunrise"],
        "sunset": data["sys"]["sunset"],
        "rain": data.get("rain", {}).get("1h", 0),
        "weather_main": data["weather"][0]["main"],
        "weather_desc": data["weather"][0]["description"],
        "timezone_offset": data.get("timezone", 0),
    }

# ---------- WEEK FORECAST ----------
def get_week_forecast_full(city):
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
                "rain": 0,
                "weather_main": None,
                "weather_desc": None,
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
        if days[day_key]["weather_main"] is None:
            days[day_key]["weather_main"] = item["weather"][0]["main"]
            days[day_key]["weather_desc"] = item["weather"][0]["description"]

    text = ""
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
        text += (
            f"*📅 {ru_weekday(day)} {day.strftime('%d.%m')}*\n"
            f"{weather_icon(v['weather_main'])} Погода: {v['weather_desc'].capitalize()} | Осадки: {rain} мм\n"
            f"🌡 День: {temp_day}°C, Ночь: {temp_night}°C\n"
            f"💧 Влажность: {humidity_avg}%\n"
            f"💨 Ветер: {wind_avg} м/с\n"
            f"🧭 Давление: {pressure_avg} мм рт.ст.\n"
            f"🌙 Луна: {moon}\n"
            f"🎯 Клев: {rating}/5 {rating_emoji(rating)}\n\n"
        )
    return text

# ---------- HANDLERS ----------
async def station(update: Update, context: ContextTypes.DEFAULT_TYPE):
    city = "Курск" if not context.args else " ".join(context.args)
    w = get_weather(city)
    tz = timedelta(seconds=w["timezone_offset"])
    now = datetime.utcnow() + tz
    hour = now.hour
    rating = bite_rating(w["pressure_mm"], w["wind"], w["humidity"], w["rain"], hour)
    sunrise = (datetime.utcfromtimestamp(w["sunrise"]) + tz).strftime("%H:%M")
    sunset = (datetime.utcfromtimestamp(w["sunset"]) + tz).strftime("%H:%M")
    text = (
        f"*🎣 Рыбацкая метео-станция*\n\n"
        f"*📍 Город:* {city}\n"
        f"*🕒 Сейчас:* {now.strftime('%H:%M')}\n\n"
        f"{weather_icon(w['weather_main'])} *Погода:* {w['weather_desc'].capitalize()} | Осадки: {w['rain']} мм\n"
        f"🌡 Воздух: {w['temp']}°C\n"
        f"💧 Влажность: {w['humidity']}%\n"
        f"💨 Ветер: {w['wind']} м/с\n"
        f"🧭 Давление: {w['pressure_mm']} мм ({pressure_comment(w['pressure_mm'])})\n"
        f"🌅 Восход: {sunrise} | 🌇 Закат: {sunset}\n"
        f"🌙 Луна: {get_moon_phase()}\n"
        f"🎯 Клев: {rating}/5 {rating_emoji(rating)}"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    city = "Курск" if not context.args else " ".join(context.args)
    forecast_text = get_week_forecast_full(city)
    await update.message.reply_text(f"*Прогноз на 5 дней для {city}:*\n\n{forecast_text}", parse_mode="Markdown")

async def expert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    question = " ".join(context.args)
    if not question:
        await update.message.reply_text("Задай вопрос о рыбалке, например: /expert Где сегодня лучше клюёт?")
        return

    prompt = f"Ты рыболовный эксперт. Ответь подробно, дружелюбно и понятно: {question}"

    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300
        )
        answer = response.choices[0].message.content
        await update.message.reply_text(answer)
    except Exception as e:
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
    
