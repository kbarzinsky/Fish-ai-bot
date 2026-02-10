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

def format_weather(weather_main: str, pop: float) -> str:
    pop_percent = round(pop * 100)
    main_map = {
        "Clear": "Ясно",
        "Clouds": "Облачно",
        "Few clouds": "Малооблачно",
        "Scattered clouds": "Рассеянные облака",
        "Broken clouds": "Облачно с прояснениями",
        "Rain": "Дождь",
        "Drizzle": "Морось",
        "Thunderstorm": "Гроза",
        "Snow": "Снег",
        "Mist": "Туман",
        "Fog": "Туман",
        "Haze": "Дымка"
    }
    emoji_map = {
        "Clear": "☀️",
        "Clouds": "☁️",
        "Few clouds": "🌤",
        "Scattered clouds": "⛅",
        "Broken clouds": "🌥",
        "Rain": "🌧",
        "Drizzle": "🌦",
        "Thunderstorm": "⛈",
        "Snow": "❄️",
        "Mist": "🌫",
        "Fog": "🌁",
        "Haze": "🌫"
    }
    main_ru = main_map.get(weather_main, weather_main)
    emoji = emoji_map.get(weather_main, "")
    if pop_percent > 0:
        return f"{emoji} {main_ru} {pop_percent}%"
    else:
        return f"{emoji} {main_ru} Без осадков"

# ---------- WEATHER ----------
def get_weather(city):
    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {"q": city, "appid": OPENWEATHER_KEY, "units": "metric", "lang": "ru"}
    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    data = r.json()
    pressure_mm = hpa_to_mm(data["main"]["pressure"], city)
    weather_main = data["weather"][0]["main"]
    pop = data.get("rain", {}).get("1h", 0) if "rain" in data else data.get("snow", {}).get("1h", 0)
    pop = pop / 1 if pop else 0
    return {
        "temp": round(data["main"]["temp"]),
        "humidity": data["main"]["humidity"],
        "wind": round(data["wind"]["speed"], 1),
        "pressure_mm": pressure_mm,
        "sunrise": data["sys"]["sunrise"],
        "sunset": data["sys"]["sunset"],
        "lat": data["coord"]["lat"],
        "lon": data["coord"]["lon"],
        "timezone_offset": data.get("timezone", 0),
        "weather_main": weather_main,
        "pop": pop
    }

def get_forecast(city):
    url = "https://api.openweathermap.org/data/2.5/forecast"
    params = {"q": city, "appid": OPENWEATHER_KEY, "units": "metric", "lang": "ru"}
    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    return r.json()

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
    weather_text = format_weather(w["weather_main"], w["pop"])

    text = (
        f"*🎣 Рыбацкая метео-станция*\n\n"
        f"*📍 Город:* {city}\n"
        f"*🕒 Сейчас:* {local_now.strftime('%H:%M')}\n\n"
        f"*🌦 Погода:* {weather_text}\n"
        f"*🌡 Воздух:* {w['temp']}°C\n"
        f"*💧 Влажность:* {w['humidity']} %\n"
        f"*💨 Ветер:* {w['wind']} м/с\n"
        f"*🧭 Давление:* {w['pressure_mm']} мм рт.ст. ({pressure_comment(w['pressure_mm'])})\n"
        f"*🌅 Восход:* {sunrise_time}\n"
        f"*🌇 Закат:* {sunset_time}\n"
        f"*🌙 Луна:* {moon}\n"
        f"*🎯 Клев:* {rating}/5 {emoji_rating_val}"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    city = "Курск"
    if context.args:
        city = " ".join(context.args)
    try:
        data = get_forecast(city)
        tz_offset = timedelta(seconds=data["city"]["timezone"])
        moon = get_moon_phase()

        days = {}
        for item in data["list"]:
            dt = datetime.utcfromtimestamp(item["dt"]) + tz_offset
            day_key = dt.date()
            if day_key not in days:
                days[day_key] = []
            days[day_key].append(item)

        weekdays = ["Пн","Вт","Ср","Чт","Пт","Сб","Вс"]
        forecast_text = ""
        count = 0

        for day, items in days.items():
            if count >= 5:
                break
            count += 1
            # Берем дневной прогноз (ближайший к 12:00)
            day_item = min(items, key=lambda x: abs(datetime.utcfromtimestamp(x["dt"]) + tz_offset - datetime.combine(day, datetime.min.time()) - timedelta(hours=12)))
            temp_day = round(day_item["main"]["temp"])
            humidity_avg = day_item["main"]["humidity"]
            wind_avg = round(day_item["wind"]["speed"],1)
            pressure_avg = hpa_to_mm(day_item["main"]["pressure"], city)
            main_weather = day_item["weather"][0]["main"]
            pop_avg = day_item.get("pop", 0)
            weather_text = format_weather(main_weather, pop_avg)
            rating = bite_rating(temp_day, pressure_avg, wind_avg, humidity_avg, None, 12)
            emoji_val = rating_emoji(rating)
            weekday_str = weekdays[day.weekday()]

            forecast_text += (
                f"*📅 {weekday_str} {day.strftime('%d.%m')}*\n"
                f"*🌦 Погода:* {weather_text}\n"
                f"🌡 Температура: {temp_day}°C\n"
                f"💧 Влажность: {humidity_avg}%\n"
                f"💨 Ветер: {wind_avg} м/с\n"
                f"🧭 Давление: {pressure_avg} мм рт.ст. ({pressure_comment(pressure_avg)})\n"
                f"🌙 Луна: {moon}\n"
                f"🎯 Клев: {rating}/5 {emoji_val}\n\n"
            )
        await update.message.reply_text(f"*Прогноз на 5 дней для {city}:*\n\n{forecast_text}", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Не удалось получить прогноз: {e}")

# ---------- MAIN ----------
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("station", station))
    app.add_handler(CommandHandler("week", week))
    print("Бот запущен! /station <город> /week <город>")
    app.run_polling()

if __name__ == "__main__":
    main()
