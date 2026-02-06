import os
import requests
from datetime import datetime, timedelta
from collections import defaultdict
from dotenv import load_dotenv

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ---------- ENV ----------
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENWEATHER_KEY = os.getenv("OPENWEATHER_KEY")

if not BOT_TOKEN or not OPENWEATHER_KEY:
    raise RuntimeError("❌ Проверь .env")

# ---------- UTILS ----------
def hpa_to_mm(hpa):
    return round(hpa * 0.75006)

def moon_phase():
    day = datetime.utcnow().day
    phases = ["🌑","🌒","🌓","🌔","🌕","🌖","🌗","🌘"]
    return phases[(day * 8 // 30) % 8]

def rating_bar(r):
    return "🎣" * r + "⚪" * (5 - r)

# ---------- WEATHER ----------
def get_weather(city):
    r = requests.get(
        "https://api.openweathermap.org/data/2.5/weather",
        params={
            "q": city,
            "appid": OPENWEATHER_KEY,
            "units": "metric",
            "lang": "ru"
        },
        timeout=10
    )
    r.raise_for_status()
    d = r.json()

    return {
        "city": f"{d['name']}, {d['sys']['country']}",
        "temp": round(d["main"]["temp"]),
        "humidity": d["main"]["humidity"],
        "wind": round(d["wind"]["speed"], 1),
        "pressure": hpa_to_mm(d["main"]["pressure"]),
        "sunrise": d["sys"]["sunrise"],
        "sunset": d["sys"]["sunset"],
        "tz": d["timezone"]
    }

# ---------- BITE ----------
def bite_rating(temp, pressure, wind, humidity, hour):
    score = 0

    if 736 <= pressure <= 742:
        score += 3
    elif 732 <= pressure <= 748:
        score += 2
    else:
        score -= 1

    if 1 <= wind <= 4:
        score += 2
    elif wind > 7:
        score -= 2

    if humidity >= 60:
        score += 1

    if hour in range(5, 10) or hour in range(18, 22):
        score += 2

    return max(1, min(5, score))

# ---------- /STATION ----------
async def station(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        city = "Курск"
        if context.args:
            city = " ".join(context.args)

        w = get_weather(city)

        now = datetime.utcnow() + timedelta(seconds=w["tz"])
        hour = now.hour

        rating = bite_rating(
            w["temp"], w["pressure"], w["wind"], w["humidity"], hour
        )

        sunrise = (datetime.utcfromtimestamp(w["sunrise"]) + timedelta(seconds=w["tz"])).strftime("%H:%M")
        sunset = (datetime.utcfromtimestamp(w["sunset"]) + timedelta(seconds=w["tz"])).strftime("%H:%M")

        text = (
            f"🎣 *Рыбацкая метеостанция от Кирюхи*\n\n"
            f"📍 *Город:* {w['city']}\n"
            f"🕒 *Сейчас:* {now.strftime('%H:%M')}\n\n"
            f"🌡 *Воздух:* {w['temp']}°C\n"
            f"💧 *Влажность:* {w['humidity']}%\n"
            f"💨 *Ветер:* {w['wind']} м/с\n"
            f"🧭 *Давление:* {w['pressure']} мм рт.ст.\n"
            f"🌅 *Восход:* {sunrise}\n"
            f"🌇 *Закат:* {sunset}\n\n"
            f"🌙 *Луна:* {moon_phase()}\n"
            f"🎯 *Клёв:* {rating}/5 {rating_bar(rating)}"
        )

        await update.message.reply_text(text, parse_mode="Markdown")

    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")
        raise

# ---------- /WEEK ----------
async def week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        city = "Курск"
        if context.args:
            city = " ".join(context.args)

        r = requests.get(
            "https://api.openweathermap.org/data/2.5/forecast",
            params={
                "q": city,
                "appid": OPENWEATHER_KEY,
                "units": "metric",
                "lang": "ru"
            },
            timeout=10
        )
        r.raise_for_status()
        data = r.json()

        days = defaultdict(list)

        for item in data["list"]:
            date = item["dt_txt"].split(" ")[0]
            days[date].append(item)

        text = f"📅 *Прогноз на 5 дней — {data['city']['name']}*\n\n"

        for date, items in list(days.items())[:5]:
            avg_temp = round(sum(i["main"]["temp"] for i in items) / len(items))
            avg_wind = round(sum(i["wind"]["speed"] for i in items) / len(items), 1)
            avg_hum = round(sum(i["main"]["humidity"] for i in items) / len(items))
            avg_press = hpa_to_mm(round(sum(i["main"]["pressure"] for i in items) / len(items)))

            text += (
                f"📆 *{date}*\n"
                f"🌡 {avg_temp}°C | 💧 {avg_hum}% | 💨 {avg_wind} м/с\n"
                f"🧭 {avg_press} мм рт.ст.\n\n"
            )

        await update.message.reply_text(text, parse_mode="Markdown")

    except Exception as e:
        await update.message.reply_text(f"❌ Не удалось получить прогноз: {e}")
        raise

# ---------- MAIN ----------
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("station", station))
    app.add_handler(CommandHandler("week", week))

    print("🤖 Бот запущен")
    app.run_polling()

if __name__ == "__main__":
    main()
    
