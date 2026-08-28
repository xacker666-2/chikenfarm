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
BOT_TOKEN = "8923655626:AAFcOSNkpT8I7ut6Mlh41pbvDYug7FHemgg"
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "твой_ключ_openrouter_здесь")

bot = telebot.TeleBot(BOT_TOKEN)

MULT1 = 4.5
MULT2 = 12500

KNOWN_BASE_INCOME = {
    25: 205e12,   # 205 трлн
    26: 775e12,   # 775 трлн
    27: 2.5e15    # 2.5 qd
}

GROWTH_RATE = 3.49

# Системный промпт для нейросети
SYSTEM_PROMPT = """Ты — личный ИИ-помощник и стратегический аналитик по игре "Куриная ферма".
Твоя задача — помогать игроку расчитывать доходы, окупаемость, слияния куриц и давать советы по оптимизации фермы.

Экономика и правила игры:
1. Денежные единицы:
   - 1 K = 1 000, 1 M = 1 000 000, 1 B = 10^9, 1 T (трлн) = 10^12
   - 1 qd = 10^15 (1 000 трлн)
   - 1 Qd = 10^18
   - 1 Sx = 10^21 (1 000 000 qd)
   - 1 Sp = 10^24 (1 000 Sx)
2. Доход:
   - Тик каждые 5 секунд (720 тиков в час).
   - Известный базовый доход за тик: L25 = 205 трлн, L26 = 775 трлн, L27 = 2.5 qd.
   - Итоговый доход за тик = BaseIncome * 4.5 * 12500.
   - Доход за час (в Sx) = (Итоговый за тик / 10^21) * 720.
3. Покупка и Слияние:
   - 100 кур 18 уровня стоят 7 Sx => 1 курица 18 уровня стоит 0.07 Sx.
   - Слияние 3-х кур уровня L даёт 1 курицу уровня L+1.
   - Для сборки 1 курицы уровня L нужно 3^(L-18) кур 18 уровня.
   - Стоимость 1 курицы L = 3^(L-18) * 0.07 Sx.
   - Бонус слияния (прирост дохода): Bonus% = (BaseIncome(L+1) - 3*BaseIncome(L)) / (3*BaseIncome(L)) * 100%.

Отвечай четко, умом и по делу, с юмором и глубоким пониманием механик куриной фермы."""

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
# 4. ИНТЕГРАЦИЯ С НЕЙРОСЕТЬЮ (OPENROUTER)
# ==============================================================================
def ask_ai(user_query: str) -> str:
    if not OPENROUTER_API_KEY or "твой_ключ" in OPENROUTER_API_KEY:
        return "⚠️ Не настроен OPENROUTER_API_KEY в переменных Render!"

    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "json"
    }
    payload = {
        "model": "meta-llama/llama-3.3-70b-instruct",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_query}
        ]
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        if response.status_code == 200:
            data = response.json()
            return data["choices"][0]["message"]["content"]
        else:
            return f" Ошибка нейросети ({response.status_code}): {response.text}"
    except Exception as e:
        return f" Ошибка соединения с ИИ: {str(e)}"

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
        "🐔 **ИИ-Помощник и Аналитик Куриной Фермы**\n\n"
        "Я могу:\n"
        "1. Рассчитывать статистику кур и слияний по кнопкам ниже.\n"
        "2. Отвечать на **любые вопросы** текстом благодаря встроенной нейросети!\n\n"
        "Спроси меня что угодно (например: *'Что выгоднее: 3 курицы 25 или одна 26?'*)"
    )
    bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=get_main_keyboard())

@bot.message_handler(func=lambda msg: msg.text.startswith("🐔 Курица "))
def handle_quick_chicken(message):
    lvl = int(message.text.split()[-1])
    st = calculate_full_stats(lvl)
    msg = (
        f"🐔 **Курица {st['level']} уровня**\n\n"
        f"🔹 Базовый доход: {format_units(st['base_inc'])}\n"
        f"⚡ Доход в час: `{st['hour_inc_sx']:.4f} Sx/час`\n"
        f"💰 Цена: `{st['cost_sx']:.2f} Sx` ({st['count18']:,} кур 18 ур.)\n"
        f"⏳ Окупаемость: `{st['payback_hours']:.2f} часов`"
    )
    bot.send_message(message.chat.id, msg, parse_mode="Markdown")

@bot.message_handler(func=lambda msg: msg.text.startswith("🔄 Слияние "))
def handle_quick_merge(message):
    lvl = int(message.text.split()[-1].split("->")[0])
    m = calculate_merge_bonus(lvl)
    msg = (
        f"🔄 **Слияние 3× [{m['level']}] ➔ 1× [{m['next_level']}]**\n\n"
        f"🔥 Бонус прироста: `+{m['bonus_pct']:.2f}%`\n"
        f"📈 Прирост дохода: `+{m['diff_hour_sx']:.2f} Sx/час`"
    )
    bot.send_message(message.chat.id, msg, parse_mode="Markdown")

@bot.message_handler(func=lambda msg: msg.text == "📊 Таблица (20-28)")
def handle_table(message):
    res = "📊 **Уровни 20–28:**\n\n`Ур | Доход/час | Цена | Окупаемость`\n`----------------------------------`\n"
    for lvl in range(20, 29):
        st = calculate_full_stats(lvl)
        res += f"`{lvl:2d} | {st['hour_inc_sx']:10.2f} | {st['cost_sx']:7.2f} | {st['payback_hours']:4.1f}ч`\n"
    bot.send_message(message.chat.id, res, parse_mode="Markdown")

# Все остальные текстовые сообщения обрабатывает НЕЙРОСЕТЬ
@bot.message_handler(func=lambda msg: True)
def handle_ai_chat(message):
    bot.send_chat_action(message.chat.id, 'typing')
    ai_response = ask_ai(message.text)
    bot.send_message(message.chat.id, ai_response, parse_mode="Markdown")

# ==============================================================================
# 6. ЗАПУСК
# ==============================================================================
if __name__ == "__main__":
    print("🚀 Куриный ИИ-бот запущен!")
    try:
        bot.remove_webhook()
    except Exception:
        pass
    bot.infinity_polling(skip_pending_commits=True)
