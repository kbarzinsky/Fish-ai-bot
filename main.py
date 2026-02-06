import requests
from datetime import datetime
from math import cos, pi
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

API_KEY = "ВСТАВЬ_СВОЙ_API_KEY"
BOT_TOKEN = "ВСТАВЬ_ТОКЕН_БОТА"

BASE_URL = "https://api.openweathermap.org/data/2.5/"

# ---------- ВСПОМОГАТЕЛЬНЫЕ ----------

def hpa_to_mmhg(hpa: float) -> int:
    return round(hpa * 0.75006)

def get_local_time(utc_ts: int, timezone: int) -> str:
    return datetime.utcfromtimestamp(utc_ts + timezone).strftime("%d.%m.%Y %H:%M")

def moon_phase(ts: int) -> str:
    synodic_month = 29.53058867
    new_moon = 592500  # 1970-01-07
    days = (ts - new_moon) / 86400
    phase = days % synodic_month

    if phase < 1.84566:
        return "🌑 Новолуние"
    elif phase < 5.53699:
        return "🌒 Растущая"
    elif phase < 9.22831:
        return "🌓 Первая четверть"
    elif phase < 12.91963:
        return "🌔 Растущая"
    elif phase < 16.61096:
        return "🌕 Полнолуние"
    elif phase < 20.30228:
        return "🌖 Убывающая"
    elif phase < 23.99361:
        return "🌗 Последняя четверть"
    else:
        return "🌘 Убывающая"

def fishing_pressure(mm: int) -> str:
    if 738 <= mm <= 745:
        return "🎣 Отличное для рыбалки"
    elif 730 <= mm < 738 or 745 < mm <= 752:
        return "🙂 Нормальное"
    else:
        return "😕 Плохое"

# ---------- /station ----------

async def station(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Напиши город: /station Курск")
        return

    city = " ".join(context.args)

    r = requests.get(
        BASE_URL + "weather",
        params={
            "q": city,
            "appid": API_KEY,
            "units": "metric",
            "lang": "ru"
        }
    )

    if r.status_code != 200:
        await update.message.reply_text("❌ Город не найден")
        return

    d = r.json()

    pressure_mm = hpa_to_mmhg(d["main"]["pressure"])
    local_time = get_local_time(d["dt"], d["timezone"])

    text = (
        f"🎣 *Рыбацкая метеостанция от Кирюхи*\n\n"
        f"📍 *{d['name']}*\n"
        f"⏰ {local_time}\n\n"
        f"🌡 Температура: {d['main']['temp']}°C\n"
        f"🤔 Ощущается: {d['main']['feels_like']}°C\n"
        f"💧 Влажность: {d['main']['humidity']}%\n"
        f"🌬 Ветер: {d['wind']['speed']} м/с\n"
        f"⬇️ Давление: {pressure_mm} мм рт.ст.\n"
        f"{fishing_pressure(pressure_mm)}\n\n"
        f"{moon_phase(d['dt'])}"
    )

    await update.message.reply_text(text, parse_mode="Markdown")

# ---------- /week ----------

async def week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Напиши город: /week Курск")
        return

    city = " ".join(context.args)

    r = requests.get(
        BASE_URL + "forecast",
        params={
            "q": city,
            "appid": API_KEY,
            "units": "metric",
            "lang": "ru"
        }
    )

    if r.status_code != 200:
        await update.message.reply_text("❌ Не удалось получить прогноз")
        return

    data = r.json()
    days = {}

    for item in data["list"]:
        date = datetime.utcfromtimestamp(item["dt"] + data["city"]["timezone"]).strftime("%d.%m")
        days.setdefault(date, []).append(item)

    text = f"📅 *Прогноз на 5 дней — {data['city']['name']}*\n\n"

    for date, items in list(days.items())[:5]:
        t = items[len(items)//2]

        pressure_mm = hpa_to_mmhg(t["main"]["pressure"])

        text += (
            f"📆 *{date}*\n"
            f"🌡 {t['main']['temp']}°C (ощущ. {t['main']['feels_like']}°C)\n"
            f"💧 {t['main']['humidity']}%\n"
            f"🌬 {t['wind']['speed']} м/с\n"
            f"⬇️ {pressure_mm} мм рт.ст.\n"
            f"{fishing_pressure(pressure_mm)}\n\n"
        )

    await update.message.reply_text(text, parse_mode="Markdown")

# ---------- ЗАПУСК ----------

app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("station", station))
app.add_handler(CommandHandler("week", week))

print("🎣 Рыбацкая метеостанция от Кирюхи запущена")
app.run_polling()
