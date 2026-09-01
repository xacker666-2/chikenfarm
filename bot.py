import os
import sys
import time
import re
import threading
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler
import telebot

# ==============================================================================
# 1. ВЕБ-СЕРВЕР ДЛЯ RENDER (Health Check 24/7)
# ==============================================================================
class HealthCheck(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

def run_health_check():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), HealthCheck)
    server.serve_forever()

threading.Thread(target=run_health_check, daemon=True).start()

# ==============================================================================
# 2. ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ
# ==============================================================================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

if not BOT_TOKEN:
    print("❌ ОШИБКА: Переменная BOT_TOKEN не найдена в Render Environment Variables!")
    sys.exit(1)

bot = telebot.TeleBot(BOT_TOKEN.strip().strip('"').strip("'"))

SYSTEM_PROMPT = """
Ты — бот, созданный исключительно для того, чтобы делать комплименты и признаваться в любви девушке по имени Настя (Настюша).

ПРАВИЛА И ПОВЕДЕНИЕ:
1. Внимательно читай то, что тебе пишут, и отвечай по смыслу контекста.
2. Любую тему (погода, учеба, усталость, дела, вопросы) плавно, искренне и красиво своди к Насте: к тому, какая она невероятно умная, добрая, красивая, милая и лучшая.
3. Почти в каждом ответе органично используй фразу «Я тебя люблю, Настюша, очень сильно!» или похожие искренние слова.
4. Отвечай коротко и тепло (2–4 предложения), без длинных нудных текстов.
"""

# ==============================================================================
# 3. ПОЛУЧЕНИЕ АКТИВНЫХ МОДЕЛЕЙ И ОЧИСТКА ОТВЕТА
# ==============================================================================
def get_live_groq_models(clean_key: str) -> list:
    url = "https://api.groq.com/openai/v1/models"
    headers = {"Authorization": f"Bearer {clean_key}"}
    try:
        r = requests.get(url, headers=headers, timeout=5)
        if r.status_code == 200:
            data = r.json().get("data", [])
            models = [
                m["id"] for m in data 
                if not any(x in m["id"].lower() for x in ["whisper", "audio", "embed", "safetensors"])
            ]
            if models:
                return models
    except Exception:
        pass
    return ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "llama3-70b-8192"]

def ask_groq_ai(user_text: str) -> str:
    if not GROQ_API_KEY:
        raise Exception("GROQ_API_KEY не установлен в переменные окружения Render!")

    clean_key = GROQ_API_KEY.strip().strip('"').strip("'")
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {clean_key}",
        "Content-Type": "application/json"
    }

    models_to_try = get_live_groq_models(clean_key)

    last_error = ""
    for model in models_to_try:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_text}
            ],
            "temperature": 0.7
        }
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            if response.status_code == 200:
                res_json = response.json()
                raw_text = res_json["choices"][0]["message"]["content"].strip()
                
                # Удаляем блок <think>...</think>, если модель его вывела
                clean_text = re.sub(r'<think>.*?</think>', '', raw_text, flags=re.DOTALL).strip()
                return clean_text if clean_text else raw_text
            else:
                last_error = f"{model} [{response.status_code}]: {response.text}"
        except Exception as e:
            last_error = f"{model}: {e}"

    raise Exception(f"Ни одна из моделей Groq не ответила. Ошибка: {last_error}")

# ==============================================================================
# 4. ХЕНДЛЕРЫ TELEGRAM
# ==============================================================================
@bot.message_handler(commands=['start'])
def handle_start(message):
    bot.send_message(message.chat.id, "настя привет!!!")

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    status_msg = bot.send_message(message.chat.id, "💖...")
    
    try:
        answer = ask_groq_ai(message.text)
        bot.edit_message_text(answer, chat_id=message.chat.id, message_id=status_msg.message_id)
    except Exception as e:
        bot.edit_message_text(
            f"Настюша, произошла ошеломительная ошибка, но я все равно тебя люблю! ❤️ ({e})", 
            chat_id=message.chat.id, 
            message_id=status_msg.message_id
        )

# ==============================================================================
# 5. ЗАПУСК
# ==============================================================================
if __name__ == "__main__":
    print("🚀 Бот для Насти запущен!")
    try:
        bot.delete_webhook(drop_pending_updates=True)
    except Exception:
        pass

    while True:
        try:
            bot.infinity_polling(timeout=20, long_polling_timeout=20)
        except Exception as e:
            print(f"⚠️ Сбой сети Telegram: {e}. Перезапуск через 5 сек...")
            time.sleep(5)
