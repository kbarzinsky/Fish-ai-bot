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

def weather_emoji(main):
    return {
        "Clear": "☀️",
        "Clouds": "☁️",
        "Rain": "🌧",
        "Drizzle": "🌦",
        "Thunderstorm": "⛈",
        "Snow": "❄️",
        "Mist": "🌫",
        "Fog": "🌫",
        "Haze": "🌫"
    }.get(main, "🌈")

def get_precipitation(weather_dict):
    main = weather_dict.get("weather_main", "")
    if main in ["Rain", "Drizzle", "Thunderstorm"]:
        return "💦 Дождь"
    elif main == "Snow":
        return "❄️ Снег"
    else:
        return "☀️ Без осадков"

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
        "timezone_offset": data.get("timezone", 0),
        "weather_main": data["weather"][0]["main"]
    }

# ---------- WEEK FORECAST ----------
def get_week_forecast_full(city):
    try:
        url = "https://api.openweathermap.org/data/2.5/forecast"
        params = {"q": city, "appid": OPENWEATHER_KEY, "units": "metric", "lang": "ru"}
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        if "list" not in data:
            return "❌ Прогноз недоступен. Проверьте город или API ключ."

        lat = data["city"]["coord"]["lat"]
        lon = data["city"]["coord"]["lon"]
        tz_offset = timedelta(seconds=data["city"]["timezone"])
        moon = get_moon_phase()
        weekdays_ru = ["Пн","Вт","Ср","Чт","Пт","Сб","Вс"]

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
            days[day_key]["weather"].append(item["weather"][0]["main"])

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

            main_weather = max(set(values["weather"]), key=values["weather"].count)
            weather_main_ru = {
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
                "Haze": "Мгла"
            }.get(main_weather, main_weather)

            precip = get_precipitation({"weather_main": main_weather})
            weather_text = f"{weather_emoji(main_weather)} {weather_main_ru}"
            if precip != "☀️ Без осадков":
                weather_text += f", {precip.replace('💦 ', '')}"

            rating = bite_rating(temp_day, pressure_avg, wind_avg, humidity_avg, None, 9)
            emoji = rating_emoji(rating)

            weekday_name = weekdays_ru[day.weekday()]
            forecast_text += (
                f"*📅 {weekday_name} {day.strftime('%d.%m')}*\n"
                f"☁️ Погода: {weather_text}\n"
                f"🌡 День: {temp_day}°C, Ночь: {temp_night}°C\n"
                f"💧 Влажность: {humidity_avg}%\n"
                f"💨 Ветер: {wind_avg} м/с\n"
                f"🧭 Давление: {pressure_avg} мм рт.ст. ({pressure_comment(pressure_avg)})\n"
                f"🌙 Луна: {moon}\n"
                f"🎯 Клев: {rating}/5 {emoji}\n\n"
            )

        return forecast_text
    except Exception as e:
        return f"❌ Не удалось получить прогноз: {e}"

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

    tz_offset = timedelta(seconds=w["timezone_offset"])
    local_now = datetime.utcnow() + tz_offset
    hour = local_now.hour
    rating = bite_rating(w["temp"], w["pressure_mm"], w["wind"], w["humidity"], None, hour)
    emoji_rating_val = rating_emoji(rating)
    sunrise_time = (datetime.utcfromtimestamp(w["sunrise"]) + tz_offset).strftime("%H:%M")
    sunset_time = (datetime.utcfromtimestamp(w["sunset"]) + tz_offset).strftime("%H:%M")
    moon = get_moon_phase()

    weather_main_ru = {
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
        "Haze": "Мгла"
    }.get(w["weather_main"], w["weather_main"])

    precip = get_precipitation({"weather_main": w["weather_main"]})
    weather_text = f"{weather_emoji(w['weather_main'])} {weather_main_ru}"
    if precip != "☀️ Без осадков":
        weather_text += f", {precip.replace('💦 ', '')}"

    text = (
        f"*🎣 Рыбацкая метео-станция от Кирюхи*\n\n"
        f"*📍 Город:* {city}\n"
        f"*🕒 Сейчас:* {local_now.strftime('%H:%M')}\n\n"
        f"☁️ Погода: {weather_text}\n"
        f"*🌡 Воздух:* {w['temp']}°C\n"
        f"*💧 Влажность:* {w['humidity']} %\n"
        f"*💨 Ветер:* {w['wind']} м/с\n"
        f"*🧭 Давление:* {w['pressure_mm']} мм рт.ст. ({pressure_comment(w['pressure_mm'])})\n"
        f"*🌅 Восход:* {sunrise_time}\n"
        f"*🌇 Закат:* {sunset_time}\n"
        f"\n🌙 Луна: {moon}\n"
        f"🎯 Клев: {rating}/5 {emoji_rating_val}"
    )

    await update.message.reply_text(text, parse_mode="Markdown")

async def week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    city = "Курск"
    if context.args:
        city = " ".join(context.args)
    forecast_text = get_week_forecast_full(city)
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
            
    
