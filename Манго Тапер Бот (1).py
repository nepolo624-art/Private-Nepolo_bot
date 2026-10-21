import asyncio
import logging
import os
import random
import sqlite3
from typing import Optional, List, Dict, Any

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    WebAppInfo,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# ------------------------------------------------------------------------------
# Конфигурация и константы
# ------------------------------------------------------------------------------
BOT_TOKEN = "8979600812:AAHn7sooelBh1JU93GwlFLLxdDaH3mkp-wI"
ADMIN_ID = 6163657119
CHANNEL_URL = "https://t.me/nep0lo_official"
DB_NAME = "mango_tapper.db"

# Ссылки на WebApp (Mini App)
MINI_APP_URL = os.getenv("MINI_APP_URL", "https://your-domain.com/index.html")

# Список манго для коллекции (от 1 до 13)
MANGO_RARITIES = [
    {"id": 1, "name": "Обычное Манго 🥭", "chance": 40.0, "bonus": 1.0},
    {"id": 2, "name": "Зеленое Манго 🍏", "chance": 25.0, "bonus": 1.1},
    {"id": 3, "name": "Сладкое Манго 🍯", "chance": 15.0, "bonus": 1.2},
    {"id": 4, "name": "Сочное Манго 🍹", "chance": 10.0, "bonus": 1.3},
    {"id": 5, "name": "Экзотическое Манго 🏝️", "chance": 5.0, "bonus": 1.5},
    {"id": 6, "name": "Тропическое Манго 🌺", "chance": 2.5, "bonus": 1.8},
    {"id": 7, "name": "Золотое Манго 🏆", "chance": 1.2, "bonus": 2.2},
    {"id": 8, "name": "Алмазное Манго 💎", "chance": 0.6, "bonus": 3.0},
    {"id": 9, "name": "Огненное Манго 🔥", "chance": 0.3, "bonus": 4.0},
    {"id": 10, "name": "Космическое Манго 🌌", "chance": 0.2, "bonus": 5.5},
    {"id": 11, "name": "Радужное Манго 🌈", "chance": 0.1, "bonus": 7.5},
    {"id": 12, "name": "Мифическое Манго 🔱", "chance": 0.07, "bonus": 10.0},
    {"id": 13, "name": "Божественное Манго 👑", "chance": 0.03, "bonus": 15.0},
]

# ------------------------------------------------------------------------------
# База данных
# ------------------------------------------------------------------------------
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Таблица пользователей
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        telegram_id INTEGER PRIMARY KEY,
        username TEXT,
        balance REAL DEFAULT 0,
        click_power INTEGER DEFAULT 1,
        click_level INTEGER DEFAULT 1,
        energy INTEGER DEFAULT 100,
        max_energy INTEGER DEFAULT 100,
        energy_regen_level INTEGER DEFAULT 1,
        autoclicker_level INTEGER DEFAULT 0,
        is_banned INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Таблица коллекции манго пользователей
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_collection (
        telegram_id INTEGER,
        mango_id INTEGER,
        count INTEGER DEFAULT 0,
        PRIMARY KEY (telegram_id, mango_id)
    )
    """)

    # Таблица промокодов
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS promocodes (
        code TEXT PRIMARY KEY,
        reward_coins REAL,
        max_uses INTEGER,
        current_uses INTEGER DEFAULT 0,
        is_active INTEGER DEFAULT 1
    )
    """)

    # Таблица использованных промокодов
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS used_promocodes (
        telegram_id INTEGER,
        code TEXT,
        used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (telegram_id, code)
    )
    """)

    # Глобальные настройки и ивенты
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS global_settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """)

    # Установка дефолтных значений ивентов, если их нет
    cursor.execute("INSERT OR IGNORE INTO global_settings (key, value) VALUES ('x2_multiplier', '0')")
    cursor.execute("INSERT OR IGNORE INTO global_settings (key, value) VALUES ('active_event', 'none')")

    conn.commit()
    conn.close()

def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

# ------------------------------------------------------------------------------
# Модель расчета стоимости прокачки
# ------------------------------------------------------------------------------
def get_upgrade_cost(current_level: int) -> int:
    """Стоимость прокачки тапа: старт от 150 монет с коэффициентом роста 2.2"""
    base_price = 150
    multiplier = 2.2
    return int(base_price * (multiplier ** (current_level - 1)))

# ------------------------------------------------------------------------------
# FSM Состояния для админки
# ------------------------------------------------------------------------------
class AdminStates(StatesGroup):
    waiting_for_ban_id = State()
    waiting_for_unban_id = State()
    waiting_for_coins_data = State()
    waiting_for_promo_data = State()

# ------------------------------------------------------------------------------
# Хэндлеры бота
# ------------------------------------------------------------------------------
router = Router()

@router.message(CommandStart())
async def cmd_start(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or "Player"

    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT is_banned FROM users WHERE telegram_id = ?", (user_id,))
    user = cursor.fetchone()

    if user and user["is_banned"]:
        await message.answer("❌ Ваш аккаунт заблокирован администратором.")
        conn.close()
        return

    if not user:
        cursor.execute(
            "INSERT INTO users (telegram_id, username) VALUES (?, ?)",
            (user_id, username)
        )
        conn.commit()

    conn.close()

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 Играть в Манго Тапер", web_app=WebAppInfo(url=MINI_APP_URL))],
        [InlineKeyboardButton(text="📢 Наш Канал", url=CHANNEL_URL)]
    ])

    await message.answer(
        f"👋 Привет, {message.from_user.first_name}!\n\n"
        f"Добро пожаловать в **Манго Тапер** 🥭!\n"
        f"Кликай по манго, прокачивай силу тапа, собирай редкие виды манго и соревнуйся в топе!\n\n"
        f"Нажми кнопку ниже, чтобы открыть Mini App и начать игру!",
        reply_markup=kb,
        parse_mode="Markdown"
    )

# --- АДМИН-ПАНЕЛЬ ---

@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚫 Забанить", callback_data="admin_ban"),
         InlineKeyboardButton(text="✅ Разбанить", callback_data="admin_unban")],
        [InlineKeyboardButton(text="💰 Выдать/Списать монеты", callback_data="admin_coins")],
        [InlineKeyboardButton(text="⚡ Тумблер x2", callback_data="admin_toggle_x2"),
         InlineKeyboardButton(text="🎉 Управление ивентами", callback_data="admin_events")],
        [InlineKeyboardButton(text="🎟 Создать промокод", callback_data="admin_create_promo")]
    ])

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM global_settings WHERE key = 'x2_multiplier'")
    x2_status = cursor.fetchone()["value"]
    cursor.execute("SELECT value FROM global_settings WHERE key = 'active_event'")
    event_status = cursor.fetchone()["value"]
    conn.close()

    await message.answer(
        f"👑 **Панель Администратора**\n\n"
        f"• Режим x2: {'🟢 Включен' if x2_status == '1' else '🔴 Выключен'}\n"
        f"• Активный ивент: `{event_status}`",
        reply_markup=kb,
        parse_mode="Markdown"
    )

@router.callback_query(F.data == "admin_toggle_x2")
async def toggle_x2(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM global_settings WHERE key = 'x2_multiplier'")
    curr = cursor.fetchone()["value"]
    new_val = "0" if curr == "1" else "1"
    
    cursor.execute("UPDATE global_settings SET value = ? WHERE key = 'x2_multiplier'", (new_val,))
    conn.commit()
    conn.close()

    await callback.answer(f"Множитель x2 {'активирован' if new_val == '1' else 'деактивирован'}!")
    await cmd_admin(callback.message)

@router.callback_query(F.data == "admin_create_promo")
async def start_promo_creation(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    await callback.message.answer("Введите данные промокода в формате:\n`КОД МОНЕТЫ ЛИМИТ`\n\nПример: `MANGO2026 1000 50`")
    await state.set_state(AdminStates.waiting_for_promo_data)

@router.message(AdminStates.waiting_for_promo_data)
async def process_promo_creation(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        parts = message.text.split()
        code = parts[0].upper()
        reward = float(parts[1])
        max_uses = int(parts[2])

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO promocodes (code, reward_coins, max_uses) VALUES (?, ?, ?)",
            (code, reward, max_uses)
        )
        conn.commit()
        conn.close()

        await message.answer(f"✅ Промокод `{code}` на {reward} монет ({max_uses} активаций) успешно создан!", parse_mode="Markdown")
    except Exception as e:
        await message.answer(f"❌ Ошибка при создании промокода: {e}")
    finally:
        await state.clear()

# ------------------------------------------------------------------------------
# Вспомогательные функции для Mini App API (или прямого вызова)
# ------------------------------------------------------------------------------

def get_leaderboard_data(limit: int = 10) -> List[Dict[str, Any]]:
    """Получение топ-игроков с любимым исключением администратора"""
    conn = get_db()
    cursor = conn.cursor()
    
    # Исключаем Telegram ID Администратора (6163657119) из публичного топа
    cursor.execute("""
        SELECT username, balance 
        FROM users 
        WHERE telegram_id != ? AND is_banned = 0
        ORDER BY balance DESC 
        LIMIT ?
    """, (ADMIN_ID, limit))
    
    rows = cursor.fetchall()
    conn.close()
    
    return [{"username": row["username"] or "Игрок", "balance": row["balance"]} for row in rows]

async def process_promocode_activation(bot: Bot, user_id: int, code: str) -> Dict[str, Any]:
    """Логика активации промокода из Mini App с уведомлением админу"""
    code = code.strip().upper()
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM promocodes WHERE code = ? AND is_active = 1", (code,))
    promo = cursor.fetchone()

    if not promo:
        conn.close()
        return {"success": False, "message": "Промокод не существует или неактивен."}

    if promo["current_uses"] >= promo["max_uses"]:
        cursor.execute("UPDATE promocodes SET is_active = 0 WHERE code = ?", (code,))
        conn.commit()
        conn.close()
        return {"success": False, "message": "Срок действия промокода истек!"}

    cursor.execute("SELECT * FROM used_promocodes WHERE telegram_id = ? AND code = ?", (user_id, code))
    if cursor.fetchone():
        conn.close()
        return {"success": False, "message": "Вы уже активировали этот промокод!"}

    # Начисление награды
    reward = promo["reward_coins"]
    cursor.execute("UPDATE users SET balance = balance + ? WHERE telegram_id = ?", (reward, user_id))
    cursor.execute("INSERT INTO used_promocodes (telegram_id, code) VALUES (?, ?)", (user_id, code))
    cursor.execute("UPDATE promocodes SET current_uses = current_uses + 1 WHERE code = ?", (code,))

    # Если исчерпан лимит — деактивируем
    if promo["current_uses"] + 1 >= promo["max_uses"]:
        cursor.execute("UPDATE promocodes SET is_active = 0 WHERE code = ?", (code,))

    # Получаем никнейм пользователя
    cursor.execute("SELECT username FROM users WHERE telegram_id = ?", (user_id,))
    user_data = cursor.fetchone()
    username = user_data["username"] if user_data else "Неизвестный"

    conn.commit()
    conn.close()

    # Уведомление администратору в ЛС
    try:
        await bot.send_message(
            chat_id=ADMIN_ID,
            text=(
                f"🎟 **Активация промокода!**\n\n"
                f"👤 **Игрок:** @{username}\n"
                f"🆔 **ID:** `{user_id}`\n"
                f"🗝 **Промокод:** `{code}`\n"
                f"🎁 **Награда:** +{reward:,.0f} монет"
            ),
            parse_mode="Markdown"
        )
    except Exception as e:
        logging.error(f"Не удалось отправить уведомление админу: {e}")

    return {"success": True, "message": f"Успешно! Получено +{reward:,.0f} монет! 🥭"}

# ------------------------------------------------------------------------------
# Фоновая авто-рассылка напоминаний
# ------------------------------------------------------------------------------

REMINDER_MESSAGES = [
    f"📢 *Напомню, у нашего проекта есть официальный Telegram-канал!*\n\n[Подписывайся на @nep0lo_official]({CHANNEL_URL}) — там публикуются промокоды, новости обновлений и анонсы ивентов!",
    "🥭 *Кстати, а ты уже собрал все редкие манго?*\n\nЗагляни в свою коллекцию в «Профиле» — вдруг тебе уже выпало Радужное или Божественное манго?",
    "⚡ *Не забывай проверять активные ивенты!*\n\nЗаходи каждый день, восстанавливай энергию и забирай больше монет в Манго Тапере!"
]

async def periodic_reminder_task(bot: Bot):
    """Каждые 4 часа отправляет случайное напоминание активным пользователям"""
    while True:
        await asyncio.sleep(4 * 3600)  # Интервал 4 часа
        
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT telegram_id FROM users WHERE is_banned = 0")
        users = cursor.fetchall()
        conn.close()

        text = random.choice(REMINDER_MESSAGES)
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎮 Играть", web_app=WebAppInfo(url=MINI_APP_URL))],
            [InlineKeyboardButton(text="📢 Наш Канал", url=CHANNEL_URL)]
        ])

        for user in users:
            try:
                await bot.send_message(
                    chat_id=user["telegram_id"],
                    text=text,
                    reply_markup=kb,
                    parse_mode="Markdown",
                    disable_web_page_preview=False
                )
                await asyncio.sleep(0.05) # Защита от лимитов Telegram API
            except Exception:
                pass

# ------------------------------------------------------------------------------
# Главная функция запуска
# ------------------------------------------------------------------------------

async def main():
    logging.basicConfig(level=logging.INFO)
    init_db()

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    # Запуск фоновых задач
    asyncio.create_task(periodic_reminder_task(bot))

    logging.info("Бот Манго Тапер успешно запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())