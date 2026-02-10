import os
import requests
from dotenv import load_dotenv

# ---------- Загрузка переменных окружения ----------
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError("❌ Не задан BOT_TOKEN")

BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

# ---------- Функции ----------
def delete_webhook():
    """Удаляем старый webhook"""
    r = requests.post(f"{BASE_URL}/deleteWebhook")
    if r.ok:
        print("✅ Webhook удалён")
    else:
        print(f"❌ Ошибка при удалении webhook: {r.text}")

def clear_updates():
    """Сбрасываем зависшие апдейты"""
    r = requests.post(f"{BASE_URL}/getUpdates", data={"offset": -1})
    if r.ok:
        print("✅ Зависшие апдейты очищены")
    else:
        print(f"❌ Ошибка при очистке апдейтов: {r.text}")

def get_webhook_info():
    """Проверяем текущее состояние webhook"""
    r = requests.get(f"{BASE_URL}/getWebhookInfo")
    if r.ok:
        info = r.json()["result"]
        if info.get("url"):
            print(f"⚠ Вебхук ещё активен: {info['url']}")
        else:
            print("✅ Webhook не установлен, можно запускать polling")
    else:
        print(f"❌ Ошибка при проверке webhook: {r.text}")

# ---------- Основной блок ----------
if __name__ == "__main__":
    print("⏳ Начинаем очистку Telegram для локального запуска бота...")
    delete_webhook()
    clear_updates()
    get_webhook_info()
    print("🎯 Готово! Теперь можно запускать бота на ПК через run_polling()")
    
