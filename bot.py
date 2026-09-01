import os
import json
import re
import time
import threading
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler
import telebot
from telebot import types

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
# 2. КЛЮЧИ И НАСТРОЙКИ
# ==============================================================================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8923655626:AAFcOSNkpT8I7ut6Mlh41pbvDYug7FHemgg")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "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")

bot = telebot.TeleBot(BOT_TOKEN)

MULT1 = 4.5
MULT2 = 12500

KNOWN_BASE_INCOME = {
    25: 205e12,   # 205 трлн
    26: 775e12,   # 775 трлн
    27: 2.5e15    # 2.5 qd
}

GROWTH_RATE = 3.49

# Системный промпт: ИИ выступает ИСКЛЮЧИТЕЛЬНО как JSON-парсер
SYSTEM_PARSER_PROMPT = """Ты — NLU-парсер для игры "Куриная ферма".
Твоя ЕДИНСТВЕННАЯ задача — разобрать текст пользователя и вернуть STRICT JSON.
НИКАКОЙ МАТЕМАТИКИ И ВЫЧИСЛЕНИЙ НЕ ДЕЛАЙ!

Верни один из 3 вариантов JSON:

Вариант 1: Если пользователь просит посчитать ВРЕМЯ накопления (например: "сколько копить 3 Sp с 2 курами 27 ур"):
{
  "type": "calc_time",
  "target_sx": <число_переведенное_в_единицы_Sx>,
  "chickens": [{"level": <int_уровень>, "count": <int_количество>}]
}
* Правила конвертации в Sx для target_sx:
  - Sp: умножь на 1000 (3 Sp = 3000)
  - Sx: оставь как есть (10 Sx = 10)
  - Qd: раздели на 1000 (500 Qd = 0.5)
  - qd: раздели на 1000000 (2.5 qd = 0.0000025)

Вариант 2: Если пользователь просит посчитать ДОХОД или СТАТИСТИКУ конкретного набора кур:
{
  "type": "calc_stats",
  "chickens": [{"level": <int>, "count": <int>}]
}

Вариант 3: Если вопрос обычный текстовый (стратегия, советы) без конкретных расчетов целей:
{
  "type": "chat",
  "text": "<твой краткий и точный ответ>"
}

ОТВЕЧАЙ ТОЛЬКО ЧИСТЫМ JSON! Без ```json, без лишних слов."""

# ==============================================================================
# 3. ТОЧНЫЙ МАТЕМАТИЧЕСКИЙ ДВИЖОК (PYTHON)
# ==============================================================================
def get_base_income(level: int) -> float:
    if level in KNOWN_BASE_INCOME:
        return KNOWN_BASE_INCOME[level]
    if level > 27:
        return KNOWN_BASE_INCOME[27] * (GROWTH_RATE ** (level - 27))
    else:
        return KNOWN_BASE_INCOME[25] / (GROWTH_RATE ** (25 - level))

def count_18_lvl(level: int) -> int:
    if level < 18:
        return 1
    return 3 ** (level - 18)

def get_cost_sx(level: int) -> float:
    if level < 18:
        return 0.07 / (3 ** (18 - level))
    return count_18_lvl(level) * 0.07

def format_units(val_in_base: float) -> str:
    if val_in_base >= 1e24:
        return f"{val_in_base / 1e24:.3f} Sp"
    elif val_in_base >= 1e21:
        return f"{val_in_base / 1e21:.3f} Sx"
    elif val_in_base >= 1e18:
        return f"{val_in_base / 1e18:.3f} Qd"
    elif val_in_base >= 1e15:
        return f"{val_in_base / 1e15:.3f} qd"
    elif val_in_base >= 1e12:
        return f"{val_in_base / 1e12:.3f} трлн"
    elif val_in_base >= 1e9:
        return f"{val_in_base / 1e9:.3f} B"
    elif val_in_base >= 1e6:
        return f"{val_in_base / 1e6:.3f} M"
    else:
        return f"{val_in_base:.2f}"

def calculate_time_exact(target_sx: float, chickens: list) -> str:
    total_tick_base = 0.0
    chicken_desc = []
    
    for c in chickens:
        lvl = int(c.get("level", 18))
        cnt = int(c.get("count", 1))
        base_item = get_base_income(lvl)
        total_tick_base += base_item * cnt * MULT1 * MULT2
        chicken_desc.append(f"{cnt}× L{lvl}")
    
    tick_sx = total_tick_base / 1e21
    hour_sx = tick_sx * 720
    
    if hour_sx <= 0:
        return "⚠️ Доход равен 0 Sx/час. Накопить невозможно."
    
    hours_needed = target_sx / hour_sx
    total_seconds = int(hours_needed * 3600)
    
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    
    time_str = ""
    if hours > 0:
        time_str += f"{hours} ч "
    if minutes > 0 or hours > 0:
        time_str += f"{minutes} мин "
    time_str += f"{seconds} сек"
    
    chickens_str = ", ".join(chicken_desc)
    target_formatted = format_units(target_sx * 1e21)
    hour_inc_formatted = format_units(hour_sx * 1e21)
    
    return (
        f"⚡ **Точный расчет (Python Engine):**\n\n"
        f"🎯 **Цель:** `{target_formatted}` (`{target_sx:.4f} Sx`)\n"
        f"🐔 **Состав фермы:** {chickens_str}\n"
        f"📈 **Доход в час:** `{hour_inc_formatted}/час` (`{hour_sx:.4f} Sx/час`)\n"
        f"⏳ **Время накопления:** **{time_str}** (`{hours_needed:.2f}` ч.)"
    )

def calculate_chickens_exact(chickens: list) -> str:
    total_tick_base = 0.0
    total_cost_sx = 0.0
    total_18 = 0
    chicken_desc = []
    
    for c in chickens:
        lvl = int(c.get("level", 18))
        cnt = int(c.get("count", 1))
        total_tick_base += get_base_income(lvl) * cnt * MULT1 * MULT2
        total_cost_sx += get_cost_sx(lvl) * cnt
        total_18 += count_18_lvl(lvl) * cnt
        chicken_desc.append(f"{cnt}× L{lvl}")
        
    hour_sx = (total_tick_base / 1e21) * 720
    payback = total_cost_sx / hour_sx if hour_sx > 0 else 0
    
    return (
        f"📊 **Расчет фермы (Python Engine):**\n\n"
        f"🐔 **Состав:** {', '.join(chicken_desc)}\n"
        f"⚡ **Доход в час:** `{hour_sx:.4f} Sx/час`\n"
        f"💰 **Суммарная цена:** `{total_cost_sx:.2f} Sx` ({total_18:,} кур 18 ур.)\n"
        f"⏳ **Окупаемость:** `{payback:.2f} часов`"
    )

def calculate_full_stats(level: int):
    base_inc = get_base_income(level)
    tick_inc_base = base_inc * MULT1 * MULT2
    tick_inc_sx = tick_inc_base / 1e21
    hour_inc_sx = tick_inc_sx * 720
    cost_sx = get_cost_sx(level)
    count18 = count_18_lvl(level)
    payback_hours = cost_sx / hour_inc_sx if hour_inc_sx > 0 else 0
    
    return {
        "level": level,
        "base_inc": base_inc,
        "hour_inc_sx": hour_inc_sx,
        "cost_sx": cost_sx,
        "count18": count18,
        "payback_hours": payback_hours
    }

def calculate_merge_bonus(level: int):
    base_l = get_base_income(level)
    base_l1 = get_base_income(level + 1)
    sum_three = 3 * base_l
    bonus_pct = ((base_l1 - sum_three) / sum_three) * 100
    hour_l = (sum_three * MULT1 * MULT2 / 1e21) * 720
    hour_l1 = (base_l1 * MULT1 * MULT2 / 1e21) * 720
    diff_hour_sx = hour_l1 - hour_l
    
    return {
        "level": level,
        "next_level": level + 1,
        "bonus_pct": bonus_pct,
        "diff_hour_sx": diff_hour_sx
    }

# ==============================================================================
# 4. ОБРАБОТКА ЗАПРОСОВ (GROQ NLU + PYTHON MATH)
# ==============================================================================
def process_user_query(user_query: str) -> str:
    key = "".join(GROQ_API_KEY.split())

    if not key:
        return "⚠️ Не настроен GROQ_API_KEY!"

    url = "[https://api.groq.com/openai/v1/chat/completions](https://api.groq.com/openai/v1/chat/completions)"
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": SYSTEM_PARSER_PROMPT},
            {"role": "user", "content": user_query}
        ],
        "temperature": 0.1
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        
        if response.status_code != 200:
            return f"⚠️ Ошибка API Groq ({response.status_code}): {response.text}"
            
        res_data = response.json()
        content = res_data["choices"][0]["message"]["content"].strip()
        
        # Очистка от markdown блоков json
        if content.startswith("```"):
            content = re.sub(r"^```[a-zA-Z]*\n?", "", content)
            content = re.sub(r"\n?```$", "", content)
            content = content.strip()
            
        data = json.loads(content)
        req_type = data.get("type")
        
        if req_type == "calc_time":
            target_sx = float(data.get("target_sx", 0))
            chickens = data.get("chickens", [])
            return calculate_time_exact(target_sx, chickens)
            
        elif req_type == "calc_stats":
            chickens = data.get("chickens", [])
            return calculate_chickens_exact(chickens)
            
        elif req_type == "chat":
            return data.get("text", "Не смог обработать ответ.")
            
        else:
            return "⚠️ Неизвестный формат данных."
            
    except json.JSONDecodeError:
        return "⚠️ Не удалось распознать параметры запроса. Укажите, например: «Сколько копить 3 Sp с 2 курами 27 ур»."
    except Exception as e:
        return f"⚠️ Ошибка обработки: {str(e)}"

def safe_send_message(chat_id: int, text: str):
    chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
    for chunk in chunks:
        try:
            bot.send_message(chat_id, chunk, parse_mode="Markdown")
        except Exception:
            bot.send_message(chat_id, chunk)

# ==============================================================================
# 5. ХЕНДЛЕРЫ TELEGRAM
# ==============================================================================
def get_main_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("🐔 Курица 25", "🐔 Курица 26", "🐔 Курица 27")
    markup.add("🔄 Слияние 25->26", "🔄 Слияние 26->27")
    markup.add("📊 Таблица (20-28)")
    return markup

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    text = (
        "🐔 **Калькулятор и Аналитик Куриной Фермы**\n\n"
        "Вычисления производятся на **100% точном Python-движке**.\n\n"
        "Примеры текстовых запросов:\n"
        "• *Сколько копить 3 Sp с 2 курами 27 ур?*\n"
        "• *Какой доход у 5 кур 26 уровня?*\n"
        "• *Сколько времени нужно на 500 Sx с 3 курами 25 уровня?*"
    )
    bot.send_message(message.chat.id, text, reply_markup=get_main_keyboard(), parse_mode="Markdown")

@bot.message_handler(func=lambda msg: msg.text and msg.text.startswith("🐔 Курица "))
def handle_quick_chicken(message):
    try:
        lvl = int(message.text.split()[-1])
        st = calculate_full_stats(lvl)
        msg = (
            f"🐔 **Курица {st['level']} уровня**\n\n"
            f"🔹 Базовый доход: {format_units(st['base_inc'])}\n"
            f"⚡ Доход в час: `{st['hour_inc_sx']:.4f} Sx/час`\n"
            f"💰 Цена: `{st['cost_sx']:.2f} Sx` ({st['count18']:,} кур 18 ур.)\n"
            f"⏳ Окупаемость: `{st['payback_hours']:.2f} часов`"
        )
        safe_send_message(message.chat.id, msg)
    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка: {e}")

@bot.message_handler(func=lambda msg: msg.text and msg.text.startswith("🔄 Слияние "))
def handle_quick_merge(message):
    try:
        lvl = int(message.text.split()[-1].split("->")[0])
        m = calculate_merge_bonus(lvl)
        msg = (
            f"🔄 **Слияние 3× [{m['level']}] ➔ 1× [{m['next_level']}]**\n\n"
            f"🔥 Бонус прироста: `+{m['bonus_pct']:.2f}%`\n"
            f"📈 Прирост дохода: `+{m['diff_hour_sx']:.2f} Sx/час`"
        )
        safe_send_message(message.chat.id, msg)
    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка: {e}")

@bot.message_handler(func=lambda msg: msg.text == "📊 Таблица (20-28)")
def handle_table(message):
    res = "📊 **Уровни 20–28 (Точный расчет):**\n\n`Ур | Доход/час | Цена | Окупаемость`\n`----------------------------------`\n"
    for lvl in range(20, 29):
        st = calculate_full_stats(lvl)
        res += f"`{lvl:2d} | {st['hour_inc_sx']:10.2f} | {st['cost_sx']:7.2f} | {st['payback_hours']:4.1f}ч`\n"
    safe_send_message(message.chat.id, res)

@bot.message_handler(func=lambda msg: True)
def handle_ai_chat(message):
    sent_msg = bot.send_message(message.chat.id, "⏳ Выполняю точный расчет...")
    response_text = process_user_query(message.text)
    
    try:
        bot.edit_message_text(response_text, chat_id=message.chat.id, message_id=sent_msg.message_id, parse_mode="Markdown")
    except Exception:
        try:
            bot.edit_message_text(response_text, chat_id=message.chat.id, message_id=sent_msg.message_id)
        except Exception:
            safe_send_message(message.chat.id, response_text)

# ==============================================================================
# 6. НЕПРЕРЫВНЫЙ ЗАПУСК С АВТОВОССТАНОВЛЕНИЕМ
# ==============================================================================
if __name__ == "__main__":
    print("🚀 Куриный Бот запущен на Groq API (NLU + Python Math Engine)!")
    
    try:
        bot.delete_webhook(drop_pending_updates=True)
    except Exception as e:
        print(f"Предупреждение вебхука: {e}")

    # Бесконечный цикл переподключения при любых разрывах сети
    while True:
        try:
            bot.infinity_polling(timeout=20, long_polling_timeout=20)
        except Exception as e:
            print(f"⚠️ Сбой сети Telegram. Перезапуск через 5 секунд... Ошибка: {e}")
            time.sleep(5)
