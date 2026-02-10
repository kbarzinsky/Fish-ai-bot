import os
import requests
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

# ---------- LOAD ENV ----------
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENWEATHER_KEY = os.getenv("OPENWEATHER_KEY")

if not BOT_TOKEN or not OPENWEATHER_KEY:
    raise RuntimeError("❌ Не заданы BOT_TOKEN или OPENWEATHER_KEY")

# ---------- CONSTANTS ----------
WEEKDAYS_RU = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]

KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton("📍 Текущий прогноз")],
        [KeyboardButton("📅 Прогноз на 5 дней")]
    ],
    resize_keyboard=True
)

# ---------- HELPERS ----------
def hpa_to_mm(hpa, city=""):
    city_altitude = {"курск": 200, "москва": 156}
    altitude = city_altitude.get(city.lower(), 0)
    return round((hpa - altitude * 0.12) * 0.75006)

def moon_phase_icon_from_value(p):
    # p in [0..1] from onecall/daily['moon_phase'] OR custom numeric; map to icon+label
    if p is None:
        return "🌙"
    if p < 0.03: return "🌑 Новолуние"
    if p < 0.22: return "🌒 Растущая"
    if p < 0.28: return "🌓 Первая четверть"
    if p < 0.47: return "🌔 Растущая"
    if p < 0.53: return "🌕 Полнолуние"
    if p < 0.72: return "🌖 Убывающая"
    if p < 0.78: return "🌗 Последняя четверть"
    return "🌘 Убывающая"

def pressure_comment(mm):
    if 735 <= mm <= 741:
        return "🌟 Отличное"
    elif mm < 735:
        return "⚠ Низкое"
    elif mm <= 750:
        return "⚠ Высоковатое"
    return "❌ Очень высокое"

def bite_rating(temp, pressure, wind, humidity, hour):
    score = 0
    if temp is None:
        temp = 10
    if 735 <= pressure <= 741:
        score += 3
    if 1 <= wind <= 4:
        score += 2
    elif wind > 7:
        score -= 1
    if humidity >= 60:
        score += 1
    if hour in range(5, 10) or hour in range(18, 22):
        score += 2
    return max(1, min(5, score))

def rating_emoji(r):
    return "🎣" * r + "⚪" * (5 - r)

def select_weather_emoji_and_text(weather):
    # weather is dict like {'id':..,'main':'Rain','description':'небольшой дождь'}
    if not weather:
        return ("🌤", "Погода")
    main = weather.get("main", "").lower()
    desc = weather.get("description", "").capitalize() or weather.get("main", "")
    if "clear" in main or "ясн" in desc.lower():
        return ("☀️", desc or "Ясно")
    if "cloud" in main or "облак" in desc.lower():
        return ("☁️", desc or "Облачно")
    if "rain" in main or "дожд" in desc.lower():
        return ("🌧", desc or "Дождь")
    if "drizzle" in main or "морос" in desc.lower():
        return ("🌦", desc or "Морось")
    if "thunder" in main or "гроза" in desc.lower():
        return ("⛈", desc or "Гроза")
    if "snow" in main or "снег" in desc.lower():
        return ("❄️", desc or "Снег")
    if "mist" in main or "туман" in desc.lower():
        return ("🌫", desc or "Туман")
    return ("🌤", desc or main.capitalize())

def format_weather_text(weather_obj, precip_mm, pop):
    # weather_obj expected from onecall entries: weather[0] dict
    emoji, desc = select_weather_emoji_and_text(weather_obj)
    pop_pct = int(round(pop * 100)) if pop is not None else 0
    parts = f"{emoji} {desc}"
    if precip_mm is not None and precip_mm > 0:
        # show mm and percent if available
        if pop is not None:
            parts += f" {precip_mm} мм ({pop_pct}%)"
        else:
            parts += f" {precip_mm} мм"
    else:
        if pop is not None and pop_pct > 0:
            parts += f" ({pop_pct}%)"
    return parts

# ---------- API helpers ----------
def get_coords_and_basic(city):
    """Call /weather to get coords and timezone (fallback). Returns dict or raises."""
    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {"q": city, "appid": OPENWEATHER_KEY, "units": "metric", "lang": "ru"}
    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    return r.json()

def get_onecall(lat, lon):
    url = "https://api.openweathermap.org/data/2.5/onecall"
    params = {"lat": lat, "lon": lon, "exclude": "minutely", "appid": OPENWEATHER_KEY, "units": "metric", "lang": "ru"}
    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    return r.json()

# ---------- HANDLERS ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎣 Рыбацкий метео-бот готов! Выбери кнопку или используй /station /week",
        reply_markup=KEYBOARD
    )

async def station(update: Update, context: ContextTypes.DEFAULT_TYPE):
    city = "Курск" if not context.args else " ".join(context.args)
    try:
        basic = get_coords_and_basic(city)
        lat = basic["coord"]["lat"]
        lon = basic["coord"]["lon"]
        one = get_onecall(lat, lon)
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка получения данных: {e}")
        return

    tz_seconds = one.get("timezone_offset", basic.get("timezone", 0))
    tz = timezone(timedelta(seconds=tz_seconds))
    now_dt = datetime.now(tz)

    current = one.get("current", {})
    daily0 = one.get("daily", [None])[0] or {}

    # precipitation: prefer current rain/snow mm, else hourly[0] or daily rain
    precip_mm = None
    if "rain" in current and isinstance(current["rain"], dict):
        precip_mm = current["rain"].get("1h", 0)
    elif "snow" in current and isinstance(current["snow"], dict):
        precip_mm = current["snow"].get("1h", 0)
    else:
        # try hourly 0
        hr0 = one.get("hourly", [{}])[0]
        if hr0:
            precip_mm = hr0.get("rain", {}).get("1h") or hr0.get("snow", {}).get("1h") or 0
        else:
            precip_mm = daily0.get("rain", 0) or daily0.get("snow", 0) or 0

    # pop for current: try hourly[0].pop then daily0.pop
    pop = None
    if one.get("hourly"):
        pop = one["hourly"][0].get("pop", None)
    if pop is None:
        pop = daily0.get("pop", None)

    weather_obj = current.get("weather", [{}])[0]
    weather_line = format_weather_text(weather_obj, precip_mm or 0, pop if pop is not None else 0)

    # temperatures: use daily0 temps if present, else current temp
    temp_day = None
    temp_night = None
    if daily0.get("temp"):
        temp_day = round(daily0["temp"].get("day"))
        temp_night = round(daily0["temp"].get("night"))
    else:
        temp_day = round(current.get("temp", 0))
        temp_night = temp_day - 4  # fallback estimate

    humidity = current.get("humidity", 0)
    wind = current.get("wind_speed", 0)
    pressure_hpa = current.get("pressure", None)
    pressure_mm = hpa_to_mm(pressure_hpa, city) if pressure_hpa is not None else None

    moon_val = daily0.get("moon_phase", None)
    moon_str = moon_phase_icon_from_value(moon_val) if moon_val is not None else "🌙"

    bite = bite_rating(temp_day, pressure_mm or 740, wind, humidity, now_dt.hour)

    text = (
        f"🎣 *Текущий прогноз*\n\n"
        f"*📍 Город:* {city}\n"
        f"*📅 День:* {WEEKDAYS_RU[now_dt.weekday()]} {now_dt.strftime('%d.%m')}\n"
        f"*🕒 Сейчас:* {now_dt.strftime('%H:%M')}\n\n"
        f"*🌦 Погода:* {weather_line}\n"
        f"*🌡 Температура:* 🌞 {temp_day}°C / 🌙 {temp_night}°C\n"
        f"*💧 Влажность:* {humidity}%\n"
        f"*💨 Ветер:* {wind} м/с\n"
        f"*🧭 Давление:* {pressure_mm} мм ({pressure_comment(pressure_mm)})\n"
        f"*🌅 Восход:* {datetime.fromtimestamp(current.get('sunrise', daily0.get('sunrise', 0)), tz).strftime('%H:%M')}\n"
        f"*🌇 Закат:* {datetime.fromtimestamp(current.get('sunset', daily0.get('sunset', 0)), tz).strftime('%H:%M')}\n"
        f"*🌙 Луна:* {moon_str}\n"
        f"*🎯 Клёв:* {bite}/5 {rating_emoji(bite)}"
    )

    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=KEYBOARD)

async def week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    city = "Курск" if not context.args else " ".join(context.args)
    try:
        basic = get_coords_and_basic(city)
        lat = basic["coord"]["lat"]
        lon = basic["coord"]["lon"]
        one = get_onecall(lat, lon)
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка получения данных: {e}")
        return

    tz_seconds = one.get("timezone_offset", basic.get("timezone", 0))
    tz = timezone(timedelta(seconds=tz_seconds))
    daily = one.get("daily", [])

    out = f"📅 *Прогноз на 5 дней для {city}:*\n\n"

    # iterate next 5 days (including today)
    for d in daily[:5]:
        if not d:
            continue
        dt = datetime.fromtimestamp(d.get("dt", 0), tz)
        weekday = WEEKDAYS_RU[dt.weekday()]
        # weather and precip
        weather_obj = d.get("weather", [{}])[0]
        precip_mm = d.get("rain", 0) or d.get("snow", 0) or 0
        pop = d.get("pop", 0)
        weather_line = format_weather_text(weather_obj, precip_mm, pop)

        temp_day = round(d.get("temp", {}).get("day")) if d.get("temp") else None
        temp_night = round(d.get("temp", {}).get("night")) if d.get("temp") else None
        humidity = d.get("humidity", 0)
        wind = d.get("wind_speed", 0)
        pressure_mm = hpa_to_mm(d.get("pressure", 1013), city)
        moon_str = moon_phase_icon_from_value(d.get("moon_phase", None))
        hour = 12  # midday rating heuristic
        bite = bite_rating(temp_day or temp_night or 10, pressure_mm, wind, humidity, hour)

        out += (
            f"📅 *{weekday} {dt.strftime('%d.%m')}*\n\n"
            f"*🌦 Погода:* {weather_line}\n"
            f"*🌡 Температура:* 🌞 {temp_day}°C / 🌙 {temp_night}°C\n"
            f"*💧 Влажность:* {humidity}%\n"
            f"*💨 Ветер:* {wind} м/с\n"
            f"*🧭 Давление:* {pressure_mm} мм ({pressure_comment(pressure_mm)})\n"
            f"*🌙 Луна:* {moon_str}\n"
            f"*🎯 Клёв:* {bite}/5 {rating_emoji(bite)}\n\n"
        )

    await update.message.reply_text(out, parse_mode="Markdown", reply_markup=KEYBOARD)

async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "📍 Текущий прогноз":
        await station(update, context)
    elif update.message.text == "📅 Прогноз на 5 дней":
        await week(update, context)

# ---------- MAIN ----------
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("station", station))
    app.add_handler(CommandHandler("week", week))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, buttons))
    print("🚀 Бот запущен")
    app.run_polling()

if __name__ == "__main__":
    main()
    
