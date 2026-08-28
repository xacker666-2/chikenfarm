import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import telebot
from telebot import types

# ==============================================================================
# 1. ВЕБ-СЕРВЕР ДЛЯ RENDER (Health Check, чтобы сервис не засыпал)
# ==============================================================================
class HealthCheck(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

def run_health_check():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), HealthCheck)
    server.serve_forever()

threading.Thread(target=run_health_check, daemon=True).start()

# ==============================================================================
# 2. НАСТРОЙКИ БОТА И ИГРОВОГО ДВИЖКА
# ==============================================================================
BOT_TOKEN = "8987466824:AAFWEREqQX_AesuWoARdTB1I5qFz7kI1CVw"  # Твой токен
bot = telebot.TeleBot(BOT_TOKEN)

# Множители дохода по умолчанию
MULT1 = 4.5
MULT2 = 12500

# Точные известные базовые доходы (за 1 тик = 5 сек)
KNOWN_BASE_INCOME = {
    25: 205e12,   # 205 трлн
    26: 775e12,   # 775 трлн
    27: 2.5e15    # 2.5 qd (2500 трлн)
}

# Средний коэффициент роста для неизвестных уровней
GROWTH_RATE = 3.49

# ==============================================================================
# 3. МАТЕМАТИЧЕСКИЙ ДВИЖОК РАСЧЁТОВ
# ==============================================================================
def get_base_income(level: int) -> float:
    """Возвращает базовый доход курицы заданного уровня."""
    if level in KNOWN_BASE_INCOME:
        return KNOWN_BASE_INCOME[level]
    if level > 27:
        return KNOWN_BASE_INCOME[27] * (GROWTH_RATE ** (level - 27))
    else:  # level < 25
        return KNOWN_BASE_INCOME[25] / (GROWTH_RATE ** (25 - level))

def count_18_lvl(level: int) -> int:
    """Количество кур 18 уровня для сборки одной курицы уровня L."""
    if level < 18:
        return 1
    return 3 ** (level - 18)

def get_cost_sx(level: int) -> float:
    """Стоимость одной курицы уровня L в Sx."""
    if level < 18:
        return 0.07 / (3 ** (18 - level))
    return count_18_lvl(level) * 0.07

def format_units(val_in_base: float) -> str:
    """Форматирует абсолютные числа в читаемые единицы (трлн, qd, Sx и т.д.)."""
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
    """Полный расчёт параметров курицы уровня L."""
    base_inc = get_base_income(level)
    tick_inc_base = base_inc * MULT1 * MULT2
    tick_inc_sx = tick_inc_base / 1e21
    hour_inc_sx = tick_inc_sx * 720  # 720 тиков в час
    
    cost_sx = get_cost_sx(level)
    count18 = count_18_lvl(level)
    
    payback_hours = cost_sx / hour_inc_sx if hour_inc_sx > 0 else 0
    
    return {
        "level": level,
        "base_inc": base_inc,
        "tick_inc_base": tick_inc_base,
        "tick_inc_sx": tick_inc_sx,
        "hour_inc_sx": hour_inc_sx,
        "cost_sx": cost_sx,
        "count18": count18,
        "payback_hours": payback_hours
    }

def calculate_merge_bonus(level: int):
    """Расчёт прироста при слиянии 3xL -> 1x(L+1)."""
    base_l = get_base_income(level)
    base_l1 = get_base_income(level + 1)
    sum_three = 3 * base_l
    
    bonus_pct = ((base_l1 - sum_three) / sum_three) * 100
    
    # Расчет чистого прироста дохода в час
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
# 4. ТЕЛЕГРАМ-ХЕНДЛЕРЫ
# ==============================================================================

def get_main_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("🐔 Курица 25", "🐔 Курица 26", "🐔 Курица 27")
    markup.add("🔄 Слияние 25->26", "🔄 Слияние 26->27")
    markup.add("📊 Сравнительная таблица (20-28)")
    return markup

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    text = (
        "🐔 **Калькулятор и Аналитик Куриной Фермы**\n\n"
        "Я умею рассчитывать:\n"
        "• Базовый и итоговый доход курицы (за тик и в час в Sx)\n"
        "• Стоимость покупки и окупаемость в часах\n"
        "• Выгоду и процент бонуса при слиянии 3 в 1\n\n"
        "👇 **Отправь мне номер уровня** (например, `27`) или воспользуйся кнопками ниже:"
    )
    bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=get_main_keyboard())

@bot.message_handler(func=lambda msg: msg.text.startswith("🐔 Курица "))
def handle_quick_chicken(message):
    try:
        lvl = int(message.text.split()[-1])
        send_chicken_info(message.chat.id, lvl)
    except Exception:
        bot.send_message(message.chat.id, "Ошибка распознавания уровня.")

@bot.message_handler(func=lambda msg: msg.text.startswith("🔄 Слияние "))
def handle_quick_merge(message):
    try:
        pair = message.text.split()[-1]
        lvl = int(pair.split("->")[0])
        send_merge_info(message.chat.id, lvl)
    except Exception:
        bot.send_message(message.chat.id, "Ошибка распознавания уровня слияния.")

@bot.message_handler(func=lambda msg: msg.text == "📊 Сравнительная таблица (20-28)")
def handle_table(message):
    res = "📊 **Сравнительные параметры уровней (20–28):**\n\n"
    res += "`Ур | Доход/час (Sx) | Цена (Sx) | Окупаемость`\n"
    res += "`------------------------------------------`\n"
    
    for lvl in range(20, 29):
        st = calculate_full_stats(lvl)
        res += f"`{lvl:2d} | {st['hour_inc_sx']:14.2f} | {st['cost_sx']:9.2f} | {st['payback_hours']:5.1f} ч`\n"
        
    bot.send_message(message.chat.id, res, parse_mode="Markdown")

def send_chicken_info(chat_id, level: int):
    st = calculate_full_stats(level)
    
    msg = (
        f"🐔 **Анализ курицы {st['level']} уровня**\n\n"
        f"🔹 **Базовый доход (за тик 5с):** {format_units(st['base_inc'])}\n"
        f"🔹 **Итоговый доход за тик (×{MULT1} ×{MULT2}):** {format_units(st['tick_inc_base'])}\n"
        f"⚡ **Доход за час:** `{st['hour_inc_sx']:.4f} Sx/час`\n\n"
        f"💰 **Стоимость 1 шт:** `{st['cost_sx']:.2f} Sx` (эквивалентно {st['count18']:,} кур 18 ур.)\n"
        f"⏳ **Время окупаемости:** `{st['payback_hours']:.2f} часов` (~{st['payback_hours']/24:.1f} дн.)"
    )
    bot.send_message(chat_id, msg, parse_mode="Markdown")

def send_merge_info(chat_id, level: int):
    m = calculate_merge_bonus(level)
    
    msg = (
        f"🔄 **Анализ слияния 3× [Уровень {m['level']}] ➔ 1× [Уровень {m['next_level']}]**\n\n"
        f"• Базовый доход 3-х кур {m['level']} ур: {format_units(m['sum_three_base'])}\n"
        f"• Базовый доход 1-й курицы {m['next_level']} ур: {format_units(m['next_base'])}\n\n"
        f"🔥 **Бонус прироста дохода:** `+{m['bonus_pct']:.2f}%`\n"
        f"📈 **Чистый прирос дохода:** `+{m['diff_hour_sx']:.2f} Sx/час`\n"
        f"(Доход поднялся с {m['hour_3l_sx']:.2f} до {m['hour_l1_sx']:.2f} Sx/час)"
    )
    bot.send_message(chat_id, msg, parse_mode="Markdown")

@bot.message_handler(func=lambda msg: True)
def handle_user_input(message):
    text = message.text.strip()
    
    # Если пользователь просто ввел число (уровень)
    if text.isdigit():
        lvl = int(text)
        if 1 <= lvl <= 100:
            send_chicken_info(message.chat.id, lvl)
        else:
            bot.send_message(message.chat.id, "Укажи уровень курицы от 1 до 100.")
    else:
        bot.send_message(message.chat.id, "Отправь число (уровень курицы), например: `27`", parse_mode="Markdown")

# ==============================================================================
# 5. ЗАПУСК БОТА
# ==============================================================================
if __name__ == "__main__":
    print("🚀 Куриный бот-расчетчик запущен!")
    bot.infinity_polling()