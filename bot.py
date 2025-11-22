import logging
import sqlite3
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import aiohttp
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Токены
BOT_TOKEN = "8365442818:AAG3d8KdGkzqnMfWExcuTQXoPzGQ2Nxx0oY"
CRYPTO_BOT_TOKEN = "490665:AAEwanehVerJ8FvFsTf81CWtyY9wSFW86aF"
ADMIN_CHAT_ID = 7973988177

# Инициализация бота
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Состояния FSM
class RegistrationStates(StatesGroup):
    waiting_for_login = State()
    waiting_for_password = State()

class LoginStates(StatesGroup):
    waiting_for_login = State()
    waiting_for_password = State()

class AddProductStates(StatesGroup):
    waiting_for_game = State()
    waiting_for_category = State()
    waiting_for_title = State()
    waiting_for_description = State()
    waiting_for_price = State()
    waiting_for_data = State()
    waiting_for_file = State()
    waiting_for_premium = State()

class PaymentStates(StatesGroup):
    waiting_for_amount = State()
    waiting_for_payment_method = State()

class ReviewStates(StatesGroup):
    waiting_for_rating = State()
    waiting_for_review = State()

class AdminStates(StatesGroup):
    waiting_for_broadcast = State()
    waiting_for_balance_change = State()
    waiting_for_new_game = State()
    waiting_for_new_category = State()

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect('shop_bot.db')
    cursor = conn.cursor()
    
    # Таблица пользователей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER UNIQUE,
            login TEXT UNIQUE,
            password TEXT,
            balance REAL DEFAULT 0,
            frozen_balance REAL DEFAULT 0,
            registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Таблица игр
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS games (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE
        )
    ''')
    
    # Таблица категорий
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id INTEGER,
            name TEXT,
            FOREIGN KEY (game_id) REFERENCES games (id)
        )
    ''')
    
    # Таблица товаров
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            seller_id INTEGER,
            game_id INTEGER,
            category_id INTEGER,
            title TEXT,
            description TEXT,
            price REAL,
            product_data TEXT,
            file_id TEXT,
            is_premium BOOLEAN DEFAULT FALSE,
            is_owner_premium BOOLEAN DEFAULT FALSE,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (seller_id) REFERENCES users (id),
            FOREIGN KEY (game_id) REFERENCES games (id),
            FOREIGN KEY (category_id) REFERENCES categories (id)
        )
    ''')
    
    # Таблица покупок
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS purchases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            buyer_id INTEGER,
            product_id INTEGER,
            amount REAL,
            payment_method TEXT,
            purchase_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (buyer_id) REFERENCES users (id),
            FOREIGN KEY (product_id) REFERENCES products (id)
        )
    ''')
    
    # Таблица отзывов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            buyer_id INTEGER,
            seller_id INTEGER,
            product_id INTEGER,
            rating INTEGER,
            review_text TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (buyer_id) REFERENCES users (id),
            FOREIGN KEY (seller_id) REFERENCES users (id),
            FOREIGN KEY (product_id) REFERENCES products (id)
        )
    ''')
    
    # Добавляем стандартные игры и категории
    cursor.execute("SELECT COUNT(*) FROM games")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO games (name) VALUES ('CS:GO'), ('Dota 2'), ('Valorant'), ('Minecraft')")
        
        cursor.execute("SELECT id FROM games WHERE name = 'CS:GO'")
        csgo_id = cursor.fetchone()[0]
        cursor.execute("INSERT INTO categories (game_id, name) VALUES (?, 'Аккаунты'), (?, 'Скины'), (?, 'Ключи')", 
                      (csgo_id, csgo_id, csgo_id))
    
    conn.commit()
    conn.close()

# Функции для работы с базой данных
def get_user_by_chat_id(chat_id: int):
    conn = sqlite3.connect('shop_bot.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE chat_id = ?", (chat_id,))
    user = cursor.fetchone()
    conn.close()
    return user

def get_user_by_login(login: str):
    conn = sqlite3.connect('shop_bot.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE login = ?", (login,))
    user = cursor.fetchone()
    conn.close()
    return user

def create_user(chat_id: int, login: str, password: str):
    conn = sqlite3.connect('shop_bot.db')
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO users (chat_id, login, password) VALUES (?, ?, ?)", 
                      (chat_id, login, password))
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        conn.close()
        return False

def get_games():
    conn = sqlite3.connect('shop_bot.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM games")
    games = cursor.fetchall()
    conn.close()
    return games

def get_categories_by_game(game_id: int):
    conn = sqlite3.connect('shop_bot.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM categories WHERE game_id = ?", (game_id,))
    categories = cursor.fetchall()
    conn.close()
    return categories

def add_product(seller_id: int, game_id: int, category_id: int, title: str, 
                description: str, price: float, product_data: str, file_id: str = None, 
                is_premium: bool = False):
    conn = sqlite3.connect('shop_bot.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO products (seller_id, game_id, category_id, title, description, 
                            price, product_data, file_id, is_premium)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (seller_id, game_id, category_id, title, description, price, product_data, file_id, is_premium))
    conn.commit()
    product_id = cursor.lastrowid
    conn.close()
    return product_id

def get_products(game_id: int = None, category_id: int = None):
    conn = sqlite3.connect('shop_bot.db')
    cursor = conn.cursor()
    
    query = '''
        SELECT p.*, u.login, g.name as game_name, c.name as category_name 
        FROM products p
        JOIN users u ON p.seller_id = u.id
        JOIN games g ON p.game_id = g.id
        JOIN categories c ON p.category_id = c.id
        WHERE p.is_active = TRUE
    '''
    params = []
    
    if game_id:
        query += " AND p.game_id = ?"
        params.append(game_id)
    if category_id:
        query += " AND p.category_id = ?"
        params.append(category_id)
    
    query += " ORDER BY p.is_owner_premium DESC, p.is_premium DESC, p.created_at DESC"
    
    cursor.execute(query, params)
    products = cursor.fetchall()
    conn.close()
    return products

def get_product_by_id(product_id: int):
    conn = sqlite3.connect('shop_bot.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT p.*, u.login, g.name as game_name, c.name as category_name 
        FROM products p
        JOIN users u ON p.seller_id = u.id
        JOIN games g ON p.game_id = g.id
        JOIN categories c ON p.category_id = c.id
        WHERE p.id = ?
    ''', (product_id,))
    product = cursor.fetchone()
    conn.close()
    return product

def update_balance(user_id: int, amount: float):
    conn = sqlite3.connect('shop_bot.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (amount, user_id))
    conn.commit()
    conn.close()

def get_user_balance(user_id: int):
    conn = sqlite3.connect('shop_bot.db')
    cursor = conn.cursor()
    cursor.execute("SELECT balance, frozen_balance FROM users WHERE id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result if result else (0, 0)

def add_purchase(buyer_id: int, product_id: int, amount: float, payment_method: str):
    conn = sqlite3.connect('shop_bot.db')
    cursor = conn.cursor()
    
    # Добавляем запись о покупке
    cursor.execute('''
        INSERT INTO purchases (buyer_id, product_id, amount, payment_method)
        VALUES (?, ?, ?, ?)
    ''', (buyer_id, product_id, amount, payment_method))
    
    # Получаем продавца
    cursor.execute("SELECT seller_id FROM products WHERE id = ?", (product_id,))
    seller_id = cursor.fetchone()[0]
    
    # Замораживаем средства у продавца
    cursor.execute("UPDATE users SET frozen_balance = frozen_balance + ? WHERE id = ?", 
                  (amount * 0.95, seller_id))  # 5% комиссия
    
    # Делаем товар неактивным
    cursor.execute("UPDATE products SET is_active = FALSE WHERE id = ?", (product_id,))
    
    conn.commit()
    conn.close()
    return seller_id

def add_review(buyer_id: int, seller_id: int, product_id: int, rating: int, review_text: str):
    conn = sqlite3.connect('shop_bot.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO reviews (buyer_id, seller_id, product_id, rating, review_text)
        VALUES (?, ?, ?, ?, ?)
    ''', (buyer_id, seller_id, product_id, rating, review_text))
    conn.commit()
    conn.close()

def get_seller_reviews(seller_id: int):
    conn = sqlite3.connect('shop_bot.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT r.*, u.login as buyer_login 
        FROM reviews r
        JOIN users u ON r.buyer_id = u.id
        WHERE r.seller_id = ?
        ORDER BY r.created_at DESC
    ''', (seller_id,))
    reviews = cursor.fetchall()
    conn.close()
    return reviews

def get_seller_rating(seller_id: int):
    conn = sqlite3.connect('shop_bot.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT AVG(rating), COUNT(*) 
        FROM reviews 
        WHERE seller_id = ?
    ''', (seller_id,))
    result = cursor.fetchone()
    conn.close()
    return result if result else (0, 0)

# Клавиатуры
def get_main_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📦 Товары"), KeyboardButton(text="➕ Добавить товар")],
            [KeyboardButton(text="👤 Профиль"), KeyboardButton(text="⚙️ Админ-панель")]
        ],
        resize_keyboard=True
    )
    return keyboard

def get_auth_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📝 Регистрация"), KeyboardButton(text="🔐 Войти")]
        ],
        resize_keyboard=True
    )
    return keyboard

def get_profile_keyboard():
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💰 Пополнить баланс", callback_data="topup_balance")],
            [InlineKeyboardButton(text="💸 Вывод средств", callback_data="withdraw")],
            [InlineKeyboardButton(text="📊 Мои отзывы", callback_data="my_reviews")],
            [InlineKeyboardButton(text="🛒 Мои покупки", callback_data="my_purchases")]
        ]
    )
    return keyboard

def get_payment_methods_keyboard():
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 СБП", callback_data="payment_sbp")],
            [InlineKeyboardButton(text="₿ Crypto Bot", callback_data="payment_crypto")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_profile")]
        ]
    )
    return keyboard

def get_premium_keyboard():
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, за 10₽", callback_data="buy_premium")],
            [InlineKeyboardButton(text="❌ Нет", callback_data="skip_premium")]
        ]
    )
    return keyboard

# Обработчики команд
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user = get_user_by_chat_id(message.chat.id)
    if user:
        await message.answer(
            "👋 Добро пожаловать в магазин!\n\n"
            "Выберите действие:",
            reply_markup=get_main_keyboard()
        )
    else:
        await message.answer(
            "👋 Добро пожаловать!\n\n"
            "Для использования бота необходимо зарегистрироваться или войти.",
            reply_markup=get_auth_keyboard()
        )

# Регистрация
@dp.message(F.text == "📝 Регистрация")
async def start_registration(message: types.Message, state: FSMContext):
    await message.answer("Введите логин для регистрации:")
    await state.set_state(RegistrationStates.waiting_for_login)

@dp.message(RegistrationStates.waiting_for_login)
async def process_login(message: types.Message, state: FSMContext):
    login = message.text.strip()
    
    if get_user_by_login(login):
        await message.answer("❌ Этот логин уже занят. Попробуйте другой:")
        return
    
    await state.update_data(login=login)
    await message.answer("Введите пароль:")
    await state.set_state(RegistrationStates.waiting_for_password)

@dp.message(RegistrationStates.waiting_for_password)
async def process_password(message: types.Message, state: FSMContext):
    password = message.text.strip()
    data = await state.get_data()
    login = data['login']
    
    if create_user(message.chat.id, login, password):
        await message.answer(
            "✅ Регистрация успешна!\n\n"
            "Теперь вы можете пользоваться ботом.",
            reply_markup=get_main_keyboard()
        )
    else:
        await message.answer("❌ Ошибка при регистрации. Попробуйте снова.")
    
    await state.clear()

# Вход
@dp.message(F.text == "🔐 Войти")
async def start_login(message: types.Message, state: FSMContext):
    await message.answer("Введите логин:")
    await state.set_state(LoginStates.waiting_for_login)

@dp.message(LoginStates.waiting_for_login)
async def process_login_input(message: types.Message, state: FSMContext):
    login = message.text.strip()
    user = get_user_by_login(login)
    
    if not user:
        await message.answer("❌ Пользователь с таким логином не найден. Попробуйте снова:")
        return
    
    await state.update_data(login=login, user_id=user[0])
    await message.answer("Введите пароль:")
    await state.set_state(LoginStates.waiting_for_password)

@dp.message(LoginStates.waiting_for_password)
async def process_password_input(message: types.Message, state: FSMContext):
    password = message.text.strip()
    data = await state.get_data()
    user_id = data['user_id']
    
    user = get_user_by_chat_id(message.chat.id)
    if user and user[3] == password:
        await message.answer(
            "✅ Вход выполнен успешно!",
            reply_markup=get_main_keyboard()
        )
    else:
        await message.answer("❌ Неверный пароль. Попробуйте снова.")
    
    await state.clear()

# Профиль
@dp.message(F.text == "👤 Профиль")
async def show_profile(message: types.Message):
    user = get_user_by_chat_id(message.chat.id)
    if not user:
        await message.answer("Сначала войдите или зарегистрируйтесь.")
        return
    
    balance, frozen_balance = get_user_balance(user[0])
    avg_rating, review_count = get_seller_rating(user[0])
    
    profile_text = (
        f"👤 Профиль пользователя\n\n"
        f"📧 Логин: {user[2]}\n"
        f"💰 Баланс: {balance:.2f}₽\n"
        f"❄️ Заморожено: {frozen_balance:.2f}₽\n"
        f"⭐️ Рейтинг: {avg_rating:.1f}/5 ({review_count} отзывов)\n"
        f"📅 Регистрация: {user[5]}"
    )
    
    await message.answer(profile_text, reply_markup=get_profile_keyboard())

# Пополнение баланса
@dp.callback_query(F.data == "topup_balance")
async def topup_balance(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите сумму пополнения (минимум 10₽):")
    await state.set_state(PaymentStates.waiting_for_amount)
    await callback.answer()

@dp.message(PaymentStates.waiting_for_amount)
async def process_topup_amount(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text)
        if amount < 10:
            await message.answer("❌ Минимальная сумма пополнения - 10₽. Попробуйте снова:")
            return
        
        await state.update_data(amount=amount)
        await message.answer(
            f"Выберите способ оплаты для пополнения на {amount}₽:",
            reply_markup=get_payment_methods_keyboard()
        )
        
    except ValueError:
        await message.answer("❌ Введите корректную сумму:")

@dp.callback_query(F.data == "payment_sbp")
async def payment_sbp(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    amount = data['amount']
    
    await callback.message.answer(
        f"💳 Для пополнения через СБП на сумму {amount}₽ напишите @nezeexsuppp"
    )
    await state.clear()
    await callback.answer()

@dp.callback_query(F.data == "payment_crypto")
async def payment_crypto(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    amount = data['amount']
    
    # Получаем курс USDT к рублю с учетом комиссии 10%
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get('https://api.binance.com/api/v3/ticker/price?symbol=USDTRUB') as resp:
                data = await resp.json()
                usdt_rate = float(data['price'])
        
        # Учитываем комиссию 10%
        usdt_amount = amount / (usdt_rate * 0.9)
        
        await callback.message.answer(
            f"₿ Для пополнения через Crypto Bot:\n\n"
            f"💵 Сумма: {amount}₽\n"
            f"📊 Курс USDT: {usdt_rate:.2f}₽ (с учетом комиссии 10%)\n"
            f"💱 К оплате: {usdt_amount:.6f} USDT\n\n"
            f"Для создания платежа используйте API Crypto Bot"
        )
        
    except Exception as e:
        await callback.message.answer("❌ Ошибка при получении курса. Попробуйте позже.")
        logger.error(f"Error getting USDT rate: {e}")
    
    await state.clear()
    await callback.answer()

# Вывод средств
@dp.callback_query(F.data == "withdraw")
async def withdraw_funds(callback: types.CallbackQuery):
    user = get_user_by_chat_id(callback.message.chat.id)
    if not user:
        await callback.answer("Ошибка!")
        return
    
    balance, frozen_balance = get_user_balance(user[0])
    available_balance = balance - frozen_balance
    
    if available_balance < 10:
        await callback.message.answer("❌ Минимальная сумма вывода - 10₽")
        await callback.answer()
        return
    
    await callback.message.answer(
        f"💸 Для вывода средств от 10₽ напишите @nezeexsuppp\n\n"
        f"💰 Доступно для вывода: {available_balance:.2f}₽"
    )
    await callback.answer()

# Добавление товара
@dp.message(F.text == "➕ Добавить товар")
async def start_add_product(message: types.Message, state: FSMContext):
    user = get_user_by_chat_id(message.chat.id)
    if not user:
        await message.answer("Сначала войдите или зарегистрируйтесь.")
        return
    
    games = get_games()
    if not games:
        await message.answer("❌ Нет доступных игр.")
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    for game in games:
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(text=game[1], callback_data=f"game_{game[0]}")
        ])
    
    await message.answer("Выберите игру:", reply_markup=keyboard)
    await state.set_state(AddProductStates.waiting_for_game)

@dp.callback_query(F.data.startswith("game_"), AddProductStates.waiting_for_game)
async def select_game(callback: types.CallbackQuery, state: FSMContext):
    game_id = int(callback.data.split("_")[1])
    await state.update_data(game_id=game_id)
    
    categories = get_categories_by_game(game_id)
    if not categories:
        await callback.message.answer("❌ Нет доступных категорий для этой игры.")
        await state.clear()
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    for category in categories:
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(text=category[2], callback_data=f"category_{category[0]}")
        ])
    
    await callback.message.answer("Выберите категорию:", reply_markup=keyboard)
    await state.set_state(AddProductStates.waiting_for_category)
    await callback.answer()

@dp.callback_query(F.data.startswith("category_"), AddProductStates.waiting_for_category)
async def select_category(callback: types.CallbackQuery, state: FSMContext):
    category_id = int(callback.data.split("_")[1])
    await state.update_data(category_id=category_id)
    await callback.message.answer("Введите название товара:")
    await state.set_state(AddProductStates.waiting_for_title)
    await callback.answer()

@dp.message(AddProductStates.waiting_for_title)
async def process_title(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text)
    await message.answer("Введите описание товара:")
    await state.set_state(AddProductStates.waiting_for_description)

@dp.message(AddProductStates.waiting_for_description)
async def process_description(message: types.Message, state: FSMContext):
    await state.update_data(description=message.text)
    await message.answer("Введите цену товара в рублях:")
    await state.set_state(AddProductStates.waiting_for_price)

@dp.message(AddProductStates.waiting_for_price)
async def process_price(message: types.Message, state: FSMContext):
    try:
        price = float(message.text)
        if price <= 0:
            await message.answer("❌ Цена должна быть положительной. Введите цену:")
            return
        
        await state.update_data(price=price)
        await message.answer("Введите данные товара (логин/пароль, ключ и т.д.):")
        await state.set_state(AddProductStates.waiting_for_data)
        
    except ValueError:
        await message.answer("❌ Введите корректную цену:")

@dp.message(AddProductStates.waiting_for_data)
async def process_data(message: types.Message, state: FSMContext):
    await state.update_data(product_data=message.text)
    await message.answer(
        "Хотите добавить премиум-размещение за 10₽? (товар будет отображаться первым)",
        reply_markup=get_premium_keyboard()
    )
    await state.set_state(AddProductStates.waiting_for_premium)

@dp.callback_query(F.data == "buy_premium", AddProductStates.waiting_for_premium)
async def buy_premium(callback: types.CallbackQuery, state: FSMContext):
    user = get_user_by_chat_id(callback.message.chat.id)
    balance, _ = get_user_balance(user[0])
    
    if balance < 10:
        await callback.message.answer("❌ Недостаточно средств для премиум-размещения")
        await finish_add_product(callback.message, state, False)
        return
    
    # Списание средств
    update_balance(user[0], -10)
    await finish_add_product(callback.message, state, True)
    await callback.answer()

@dp.callback_query(F.data == "skip_premium", AddProductStates.waiting_for_premium)
async def skip_premium(callback: types.CallbackQuery, state: FSMContext):
    await finish_add_product(callback.message, state, False)
    await callback.answer()

async def finish_add_product(message: types.Message, state: FSMContext, is_premium: bool):
    data = await state.get_data()
    user = get_user_by_chat_id(message.chat.id)
    
    product_id = add_product(
        seller_id=user[0],
        game_id=data['game_id'],
        category_id=data['category_id'],
        title=data['title'],
        description=data['description'],
        price=data['price'],
        product_data=data['product_data'],
        is_premium=is_premium
    )
    
    premium_text = " с премиум-размещением" if is_premium else ""
    await message.answer(f"✅ Товар успешно добавлен{premium_text}!")
    await state.clear()

# Просмотр товаров
@dp.message(F.text == "📦 Товары")
async def show_products(message: types.Message):
    games = get_games()
    if not games:
        await message.answer("❌ Нет доступных товаров.")
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    for game in games:
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(text=game[1], callback_data=f"show_game_{game[0]}")
        ])
    
    await message.answer("Выберите игу для просмотра товаров:", reply_markup=keyboard)

@dp.callback_query(F.data.startswith("show_game_"))
async def show_game_products(callback: types.CallbackQuery):
    game_id = int(callback.data.split("_")[2])
    products = get_products(game_id=game_id)
    
    if not products:
        await callback.message.answer("❌ Нет товаров в этой игре.")
        await callback.answer()
        return
    
    for product in products[:10]:  # Показываем первые 10 товаров
        premium_badge = "🏆 ПРЕМИУМ " if product[9] else ""
        owner_badge = "👑 ОТ ВЛАДЕЛЬЦА " if product[10] else ""
        
        product_text = (
            f"{premium_badge}{owner_badge}\n"
            f"🎮 Игра: {product[14]}\n"
            f"📂 Категория: {product[15]}\n"
            f"📦 Название: {product[4]}\n"
            f"📝 Описание: {product[5]}\n"
            f"💰 Цена: {product[6]:.2f}₽\n"
            f"👤 Продавец: {product[13]}\n"
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🛒 Купить", callback_data=f"buy_{product[0]}")
        ]])
        
        await callback.message.answer(product_text, reply_markup=keyboard)
    
    await callback.answer()

# Покупка товара
@dp.callback_query(F.data.startswith("buy_"))
async def buy_product(callback: types.CallbackQuery):
    product_id = int(callback.data.split("_")[1])
    product = get_product_by_id(product_id)
    
    if not product:
        await callback.answer("❌ Товар не найден!")
        return
    
    user = get_user_by_chat_id(callback.message.chat.id)
    if not user:
        await callback.answer("❌ Сначала войдите!")
        return
    
    if user[0] == product[1]:
        await callback.answer("❌ Нельзя купить свой товар!")
        return
    
    balance, _ = get_user_balance(user[0])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    
    if balance >= product[6]:
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(text="💳 Оплатить балансом", callback_data=f"pay_balance_{product_id}")
        ])
    
    keyboard.inline_keyboard.append([
        InlineKeyboardButton(text="₿ Оплатить Crypto Bot", callback_data=f"pay_crypto_{product_id}")
    ])
    
    await callback.message.answer(
        f"🛒 Покупка товара: {product[4]}\n"
        f"💰 Цена: {product[6]:.2f}₽\n\n"
        f"Выберите способ оплаты:",
        reply_markup=keyboard
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("pay_balance_"))
async def pay_with_balance(callback: types.CallbackQuery):
    product_id = int(callback.data.split("_")[2])
    product = get_product_by_id(product_id)
    user = get_user_by_chat_id(callback.message.chat.id)
    
    balance, _ = get_user_balance(user[0])
    
    if balance < product[6]:
        await callback.answer("❌ Недостаточно средств!")
        return
    
    # Списание средств
    update_balance(user[0], -product[6])
    
    # Оформление покупки
    seller_id = add_purchase(user[0], product_id, product[6], "balance")
    
    # Выдача товара
    await callback.message.answer(
        f"✅ Покупка успешна!\n\n"
        f"📦 Товар: {product[4]}\n"
        f"💰 Сумма: {product[6]:.2f}₽\n\n"
        f"📋 Данные товара:\n{product[7]}"
    )
    
    # Уведомление продавцу
    seller = get_user_by_chat_id(seller_id)
    if seller:
        await bot.send_message(
            seller[1],
            f"💰 Ваш товар '{product[4]}' продан за {product[6]:.2f}₽!\n"
            f"Средства будут доступны для вывода через 24 часа."
        )
    
    # Запрос отзыва
    await asyncio.sleep(2)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    for i in range(1, 6):
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(text="⭐" * i, callback_data=f"rate_{seller_id}_{product_id}_{i}")
        ])
    
    await callback.message.answer(
        "Пожалуйста, оцените продавца:",
        reply_markup=keyboard
    )
    
    await callback.answer()

# Админ-панель
@dp.message(F.text == "⚙️ Админ-панель")
async def admin_panel(message: types.Message):
    if message.chat.id != ADMIN_CHAT_ID:
        await message.answer("❌ Доступ запрещен!")
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="💰 Изменить баланс", callback_data="admin_balance")],
        [InlineKeyboardButton(text="🎮 Добавить игру", callback_data="admin_add_game")],
        [InlineKeyboardButton(text="📂 Добавить категорию", callback_data="admin_add_category")],
        [InlineKeyboardButton(text="🗑 Удалить товар", callback_data="admin_delete_product")],
        [InlineKeyboardButton(text="🏆 Премиум товар", callback_data="admin_premium_product")]
    ])
    
    await message.answer("⚙️ Админ-панель:", reply_markup=keyboard)

@dp.callback_query(F.data == "admin_stats")
async def admin_stats(callback: types.CallbackQuery):
    if callback.message.chat.id != ADMIN_CHAT_ID:
        await callback.answer("❌ Доступ запрещен!")
        return
    
    conn = sqlite3.connect('shop_bot.db')
    cursor = conn.cursor()
    
    # Статистика пользователей
    cursor.execute("SELECT COUNT(*) FROM users")
    users_count = cursor.fetchone()[0]
    
    # Статистика товаров
    cursor.execute("SELECT COUNT(*) FROM products")
    products_count = cursor.fetchone()[0]
    
    # Статистика продаж
    cursor.execute("SELECT COUNT(*), SUM(amount) FROM purchases")
    sales_data = cursor.fetchone()
    sales_count = sales_data[0]
    total_revenue = sales_data[1] or 0
    
    conn.close()
    
    stats_text = (
        f"📊 Статистика бота:\n\n"
        f"👥 Пользователей: {users_count}\n"
        f"📦 Товаров: {products_count}\n"
        f"💰 Продаж: {sales_count}\n"
        f"💵 Общий оборот: {total_revenue:.2f}₽"
    )
    
    await callback.message.answer(stats_text)
    await callback.answer()

# Запуск бота
async def main():
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
