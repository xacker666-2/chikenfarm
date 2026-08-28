import os
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

bot = telebot.TeleBot(BOT_TOKEN)

MULT1 = 4.5
MULT2 = 12500

KNOWN_BASE_INCOME = {
    25: 205e12,   # 205 трлн
    26: 775e12,   # 775 трлн
    27: 2.5e15    # 2.5 qd
}

GROWTH_RATE = 3.49

# Строгий системный промпт с выводом базы данных и требованием краткости
SYSTEM_PROMPT = """Ты — стратегический аналитик мобильной игры "Куриная ферма".
Твоя задача — давать МАКСИМАЛЬНО КРАТКИЕ, чёткие, структурированные ответы строго по делу. Без лишней воды.

Твоя текущая база данных (синхронизация с игроком):
- Множители дохода: 4.5 и 12,500
- Базовый доход: L25 = 205 трлн, L26 = 775 трлн, L27 = 2.5 qd
- Коэффициент роста базы: 3.49
- Тик: каждые 5 сек (720 тиков в час)
- Стоимость: 100 кур 18 уровня = 7 Sx (1 шт = 0.07 Sx), слияние 3 в 1.

ПРАВИЛО: В самом начале своего ответа всегда в первой строчке коротко выводи текущие параметры базы (например: `📌 [База: Множители 4.5×12.5k | L25=205т | L26=775т | L27=2.5qd]`), чтобы подтвердить синхронизацию данных с игроком."""

# ==============================================================================
# 3. МАТЕМАТИЧЕСКИЙ ДВИЖОК
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
        return f"{val_in_base / 1e24:.2f} Sp"
    elif val_in_base >= 1e21:
        return f"{val_in_base / 1e21:.2f} Sx"
    elif val_in_base >= 1e18:
        return f"{val_in_base / 1e18:.2f} Qd"
    elif val_in_base >= 1e15:
        return f"{val_in_base / 1e15:.2f} qd"
    elif val_in_base >= 1e12:
        return f"{val_in_base / 1e12:.2f} трлн"
    elif val_in_base >= 1e9:
        return f"{val_in_base / 1e9:.2f} B"
    elif val_in_base >= 1e6:
        return f"{val_in_base / 1e6:.2f} M"
    elif val_in_base >= 1e3:
        return f"{val_in_base / 1e3:.2f} K"
    else:
        return f"{val_in_base:.2f}"

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
        "tick_inc_base": tick_inc_base,
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
        "sum_three_base": sum_three,
        "next_base": base_l1,
        "bonus_pct": bonus_pct,
        "hour_3l_sx": hour_l,
        "hour_l1_sx": hour_l1,
        "diff_hour_sx": diff_hour_sx
    }

# ==============================================================================
# 4. ИНТЕГРАЦИЯ С НЕЙРОСЕТЬЮ
# ==============================================================================
def ask_ai(user_query: str) -> str:
    raw_key = os.environ.get("OPENROUTER_API_KEY", "")
    key = "".join(raw_key.split())

    if not key or "твой_ключ" in key:
        return "⚠️ Не настроен OPENROUTER_API_KEY в переменных окружения Render!"

    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "meta-llama/llama-3.3-70b-instruct",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_query}
        ]
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=25)
        if response.status_code == 200:
            data = response.json()
            return data["choices"][0]["message"]["content"]
        else:
            return f"⚠️ Ошибка нейросети ({response.status_code}): {response.text}"
    except requests.exceptions.Timeout:
        return "⚠️ Сервер ИИ не ответил за отведенное время."
    except Exception as e:
        return f"⚠️ Ошибка соединения с ИИ: {str(e)}"

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
        "🐔 **ИИ-Помощник Куриной Фермы**\n\n"
        "📌 *Текущая база данных:*\n"
        "• Множители: 4.5 и 12,500\n"
        "• Базы: L25=205 трлн, L26=775 трлн, L27=2.5 qd\n\n"
        "Используй кнопки ниже или пиши вопросы текстом!"
    )
    bot.send_message(message.chat.id, text, reply_markup=get_main_keyboard(), parse_mode="Markdown")

@bot.message_handler(func=lambda msg: msg.text.startswith("🐔 Курица "))
def handle_quick_chicken(message):
    try:
        lvl = int(message.text.split()[-1])
        st = calculate_full_stats(lvl)
        msg = (
            f"📌 `[База: Множители 4.5×12.5k | L{lvl}]`\n\n"
            f"🐔 **Курица {st['level']} уровня**\n"
            f"🔹 Базовый доход: {format_units(st['base_inc'])}\n"
            f"⚡ Доход в час: `{st['hour_inc_sx']:.4f} Sx/час`\n"
            f"💰 Цена: `{st['cost_sx']:.2f} Sx` ({st['count18']:,} кур 18 ур.)\n"
            f"⏳ Окупаемость: `{st['payback_hours']:.2f} часов`"
        )
        safe_send_message(message.chat.id, msg)
    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка: {e}")

@bot.message_handler(func=lambda msg: msg.text.startswith("🔄 Слияние "))
def handle_quick_merge(message):
    try:
        lvl = int(message.text.split()[-1].split("->")[0])
        m = calculate_merge_bonus(lvl)
        msg = (
            f"📌 `[База: Слияние {m['level']}->{m['next_level']}]`\n\n"
            f"🔄 **Слияние 3× [{m['level']}] ➔ 1× [{m['next_level']}]**\n"
            f"🔥 Бонус прироста: `+{m['bonus_pct']:.2f}%`\n"
            f"📈 Прирост дохода: `+{m['diff_hour_sx']:.2f} Sx/час`"
        )
        safe_send_message(message.chat.id, msg)
    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка: {e}")

@bot.message_handler(func=lambda msg: msg.text == "📊 Таблица (20-28)")
def handle_table(message):
    res = "📊 **Уровни 20–28 (База проверена):**\n\n`Ур | Доход/час | Цена | Окупаемость`\n`----------------------------------`\n"
    for lvl in range(20, 29):
        st = calculate_full_stats(lvl)
        res += f"`{lvl:2d} | {st['hour_inc_sx']:10.2f} | {st['cost_sx']:7.2f} | {st['payback_hours']:4.1f}ч`\n"
    safe_send_message(message.chat.id, res)

# Текстовые запросы к ИИ с изменяющимся сообщением «Думаю...»
@bot.message_handler(func=lambda msg: True)
def handle_ai_chat(message):
    # Отправляем начальное сообщение статуса
    sent_msg = bot.send_message(message.chat.id, "⏳ Думаю и сверяю базу данных...")
    
    # Получаем ответ от ИИ
    ai_response = ask_ai(message.text)
    
    # Редактируем сообщение вместо отправки нового
    try:
        bot.edit_message_text(ai_response, chat_id=message.chat.id, message_id=sent_msg.message_id, parse_mode="Markdown")
    except Exception:
        try:
            bot.edit_message_text(ai_response, chat_id=message.chat.id, message_id=sent_msg.message_id)
        except Exception:
            safe_send_message(message.chat.id, ai_response)

# ==============================================================================
# 6. ЗАПУСК
# ==============================================================================
if __name__ == "__main__":
    print("🚀 Куриный ИИ-бот запущен!")
    try:
        bot.delete_webhook(drop_pending_updates=True)
    except Exception as e:
        print(f"Ошибка сброса вебхука: {e}")
    
    bot.infinity_polling(timeout=20, long_polling_timeout=20)
