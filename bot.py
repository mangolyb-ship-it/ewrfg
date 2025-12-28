import asyncio
import logging
import sqlite3
from datetime import datetime
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command, StateFilter
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Токен бота
BOT_TOKEN = "8518906584:AAH3ibspMsIjekNfeqYKlTG6E_v-cHEcGns"

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN, parse_mode='HTML')
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()
dp.include_router(router)

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    # Таблица пользователей
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        full_name TEXT,
        agreement_accepted BOOLEAN DEFAULT FALSE,
        registration_date DATETIME
    )
    ''')
    
    # Таблица заказов
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS orders (
        order_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        order_date DATETIME,
        category TEXT,
        platform TEXT DEFAULT 'Не указано',
        description TEXT,
        currency TEXT,
        budget TEXT,
        status TEXT DEFAULT 'новый',
        admin_comment TEXT DEFAULT NULL,
        FOREIGN KEY (user_id) REFERENCES users (user_id)
    )
    ''')
    
    # Таблица админов
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS admin_ids (
        admin_id INTEGER PRIMARY KEY
    )
    ''')
    
    # Добавление админа по умолчанию
    cursor.execute('INSERT OR IGNORE INTO admin_ids (admin_id) VALUES (1514979458)')
    
    conn.commit()
    conn.close()

# Классы состояний для FSM
class OrderStates(StatesGroup):
    waiting_for_category = State()
    waiting_for_platform = State()
    waiting_for_description = State()
    waiting_for_currency = State()
    waiting_for_budget = State()
    waiting_for_confirmation = State()

class AdminStates(StatesGroup):
    waiting_for_rejection_reason = State()

# Функции работы с БД
def add_user(user_id, username, full_name):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('''
    INSERT OR IGNORE INTO users (user_id, username, full_name, registration_date)
    VALUES (?, ?, ?, ?)
    ''', (user_id, username, full_name, datetime.now()))
    conn.commit()
    conn.close()

def update_user_agreement(user_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET agreement_accepted = TRUE WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

def check_agreement(user_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT agreement_accepted FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result and result[0]

def is_admin(user_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT admin_id FROM admin_ids WHERE admin_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return bool(result)

def create_order(user_id, category, platform, description, currency, budget):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('''
    INSERT INTO orders (user_id, order_date, category, platform, description, currency, budget, status)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (user_id, datetime.now(), category, platform, description, currency, budget, 'новый'))
    order_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return order_id

def get_user_orders(user_id, limit=10):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('''
    SELECT order_id, category, status, order_date 
    FROM orders 
    WHERE user_id = ? 
    ORDER BY order_date DESC 
    LIMIT ?
    ''', (user_id, limit))
    orders = cursor.fetchall()
    conn.close()
    return orders

def get_order_details(order_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('''
    SELECT o.*, u.username, u.full_name 
    FROM orders o 
    JOIN users u ON o.user_id = u.user_id 
    WHERE o.order_id = ?
    ''', (order_id,))
    order = cursor.fetchone()
    conn.close()
    return order

def update_order_status(order_id, status, comment=None):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    if comment:
        cursor.execute('UPDATE orders SET status = ?, admin_comment = ? WHERE order_id = ?', 
                      (status, comment, order_id))
    else:
        cursor.execute('UPDATE orders SET status = ? WHERE order_id = ?', (status, order_id))
    conn.commit()
    conn.close()

def get_orders_by_status(status):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT order_id, user_id, category, order_date FROM orders WHERE status = ? ORDER BY order_date DESC', (status,))
    orders = cursor.fetchall()
    conn.close()
    return orders

def get_all_orders():
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM orders ORDER BY order_date DESC')
    orders = cursor.fetchall()
    conn.close()
    return orders

def get_statistics():
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*) FROM users')
    total_users = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM orders WHERE status = "новый"')
    new_orders = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM orders WHERE status IN ("в обработке", "принят")')
    in_progress = cursor.fetchone()[0]
    
    conn.close()
    return total_users, new_orders, in_progress

def get_user_info(user_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT username, full_name, registration_date FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()
    conn.close()
    return user

# Хэндлеры

# Главное меню
def get_main_menu(user_id):
    keyboard = [
        [InlineKeyboardButton(text="🛠️ Заказать проект", callback_data="order_project")],
        [InlineKeyboardButton(text="👤 Профиль", callback_data="profile")],
        [InlineKeyboardButton(text="ℹ️ Информация", callback_data="info")],
        [InlineKeyboardButton(text="📊 Портфолио", callback_data="portfolio")],
        [InlineKeyboardButton(text="📞 Связаться", callback_data="contact")],
    ]
    
    if is_admin(user_id):
        keyboard.append([InlineKeyboardButton(text="⚙️ Админ-панель", callback_data="admin_panel")])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

@router.message(Command("start"))
async def cmd_start(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username
    full_name = message.from_user.full_name
    
    # Добавляем пользователя в БД
    add_user(user_id, username, full_name)
    
    # Проверяем, принял ли пользователь соглашение
    if check_agreement(user_id):
        await message.answer(
            "👋 Добро пожаловать!\n\n"
            "Выберите действие в меню ниже:",
            reply_markup=get_main_menu(user_id)
        )
    else:
        await message.answer(
            "📜 <b>ПОЛЬЗОВАТЕЛЬСКОЕ СОГЛАШЕНИЕ И ПОЛИТИКА КОНФИДЕНЦИАЛЬНОСТИ</b>\n\n"
            "Настоящее Соглашение регулирует отношения между вами (Пользователем) и CodeForge (Администрацией) по использованию услуг бота для оформления заказов на разработку сайтов и чат-ботов.\n\n"
            "<b>1. ОБЩИЕ ПОЛОЖЕНИЯ</b>\n"
            "1.1. Используя бота, вы подтверждаете, что ознакомились с условиями настоящего Соглашения и принимаете их в полном объеме.\n"
            "1.2. Бот предоставляет услуги по оформлению заказов на разработку цифровых продуктов.\n"
            "1.3. Администрация оставляет за собой право изменять условия Соглашения без предварительного уведомления.\n\n"
            "<b>2. ПРАВА И ОБЯЗАННОСТИ СТОРОН</b>\n"
            "<b>2.1. Пользователь обязуется:</b>\n"
            "• Предоставлять достоверную и актуальную информацию при оформлении заказа\n"
            "• Не нарушать законодательство Российской Федерации и стран СНГ\n"
            "• Уважать права других пользователей и Администрации\n"
            "• Не использовать бота для рассылки спама или запрещенного контента\n\n"
            "<b>2.2. Администрация обязуется:</b>\n"
            "• Обеспечивать работоспособность бота в соответствии с Режимом работы\n"
            "• Защищать персональные данные пользователей в соответствии с законодательством РФ\n"
            "• Рассматривать заявки в разумные сроки\n"
            "• Предоставлять информацию о статусе заказа\n\n"
            "<b>3. ПОРЯДОК ОФОРМЛЕНИЯ И ИСПОЛНЕНИЯ ЗАКАЗОВ</b>\n"
            "3.1. Заказ считается оформленным после заполнения всех обязательных полей и подтверждения пользователем.\n"
            "3.2. Администрация вправе отказать в выполнении заказа без объяснения причин.\n"
            "3.3. Все заказы выполняются в соответствии с техническим заданием, согласованным сторонами.\n"
            "3.4. Оплата осуществляется по договоренности после согласования ТЗ и сроков выполнения.\n\n"
            "<b>4. КОНФИДЕНЦИАЛЬНОСТЬ И ЗАЩИТА ДАННЫХ</b>\n"
            "4.1. Администрация обязуется не передавать персональные данные пользователей третьим лицам без согласия пользователя, за исключением случаев, предусмотренных законодательством РФ.\n"
            "4.2. Все коммерческие предложения, технические задания и иная коммерческая информация, передаваемая в процессе оформления заказа, является конфиденциальной.\n"
            "4.3. Администрация принимает все необходимые меры для защиты персональных данных пользователей от несанкционированного доступа.\n\n"
            "<b>5. ОТВЕТСТВЕННОСТЬ СТОРОН</b>\n"
            "<b>5.1. Администрация не несет ответственности за:</b>\n"
            "• Задержки в работе бота, вызванные техническими неполадками\n"
            "• Некорректную информацию, предоставленную пользователем\n"
            "• Последствия использования разработанных продуктов\n\n"
            "<b>5.2. Пользователь несет полную ответственность за:</b>\n"
            "• Достоверность предоставляемой информации\n"
            "• Соблюдение законодательства при использовании услуг\n"
            "• Сохранность своих учетных данных\n\n"
            "<b>6. РЕЖИМ РАБОТЫ</b>\n"
            "6.1. Бот работает круглосуточно для оформления заказов.\n"
            "6.2. Обработка заказов и консультации осуществляются в следующем режиме:\n"
            "• Понедельник - Пятница: 14:00 - 23:00\n"
            "• Суббота: 9:00 - 23:00\n"
            "• Воскресенье: выходной\n\n"
            "<b>7. ЗАКЛЮЧИТЕЛЬНЫЕ ПОЛОЖЕНИЯ</b>\n"
            "7.1. Настоящее Соглашение регулируется законодательством Российской Федерации.\n"
            "7.2. Все споры решаются путем переговоров, а при недостижении согласия - в судебном порядке по месту нахождения Администрации.\n"
            "7.3. Используя бота, вы подтверждаете свое совершеннолетие и дееспособность.\n\n"
            "<b>Нажимая \"✅ Принять соглашение\", вы подтверждаете, что ознакомились со всеми условиями и принимаете их в полном объеме.</b>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="✅ Принять соглашение", callback_data="accept_agreement")
            ]])
        )

@router.callback_query(F.data == "accept_agreement")
async def accept_agreement(callback: CallbackQuery):
    user_id = callback.from_user.id
    update_user_agreement(user_id)
    
    await callback.message.edit_text(
        "✅ Соглашение принято!\n\n"
        "👋 Добро пожаловать в CodeForge!\n"
        "Выберите действие в меню ниже:",
        reply_markup=get_main_menu(user_id)
    )
    await callback.answer()

# Главное меню хэндлеры
@router.callback_query(F.data == "order_project")
async def order_project(callback: CallbackQuery, state: FSMContext):
    await state.set_state(OrderStates.waiting_for_category)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🤖 Чат-бот", callback_data="category_chatbot")],
        [InlineKeyboardButton(text="🌐 Сайт", callback_data="category_website")],
        [InlineKeyboardButton(text="💼 Другое", callback_data="category_other")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")]
    ])
    
    await callback.message.edit_text(
        "🛠️ <b>Заказ проекта</b>\n\n"
        "Выберите категорию проекта:",
        reply_markup=keyboard
    )
    await callback.answer()

@router.callback_query(F.data == "profile")
async def profile(callback: CallbackQuery):
    user_id = callback.from_user.id
    user_info = get_user_info(user_id)
    
    if user_info:
        username, full_name, reg_date = user_info
        text = (
            f"👤 <b>Ваш профиль</b>\n\n"
            f"ID: <code>{user_id}</code>\n"
            f"Юзернейм: @{username if username else 'не указан'}\n"
            f"Имя: {full_name}\n"
            f"Дата регистрации: {reg_date}"
        )
    else:
        text = "Информация о профиле не найдена."
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📜 История заказов", callback_data="order_history")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()

@router.callback_query(F.data == "order_history")
async def order_history(callback: CallbackQuery):
    user_id = callback.from_user.id
    orders = get_user_orders(user_id)
    
    if orders:
        text = "📜 <b>Ваши последние заказы:</b>\n\n"
        for order in orders:
            order_id, category, status, order_date = order
            text += f"<b>Заказ #{order_id}</b>\n"
            text += f"Категория: {category}\n"
            text += f"Статус: {status}\n"
            text += f"Дата: {order_date}\n"
            text += "─" * 20 + "\n"
    else:
        text = "📭 У вас пока нет заказов."
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад в профиль", callback_data="profile")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()

@router.callback_query(F.data == "info")
async def info(callback: CallbackQuery):
    text = (
        "ℹ️ <b>CodeForge - разработка цифровых решений</b>\n\n"
        "<b>Наши услуги:</b>\n"
        "🤖 Чат-боты - Telegram, ВКонтакте\n"
        "🌐 Сайты - Landing Pages, интернет-магазины\n"
        "💻 Автоматизация - парсеры, интеграции\n\n"
        "<b>Стоимость определяется:</b>\n"
        "• Сложностью и объемом работ\n"
        "• Техническими требованиями\n"
        "• Срочностью выполнения\n\n"
        "<b>Режим работы:</b>\n"
        "Понедельник: 15:00 - 23:00\n"
        "Вторник: 14:00 - 23:00\n"
        "Среда: 16:00 - 23:00\n"
        "Четверг: 14:00 - 23:00\n"
        "Пятница: 14:00 - 23:00\n"
        "Суббота: 9:00 - 23:00\n"
        "Воскресенье: выходной (берём заказы)"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()

@router.callback_query(F.data == "portfolio")
async def portfolio(callback: CallbackQuery):
    text = (
        "📊 <b>Портфолио</b>\n\n"
        "<b>🤖 Чат-боты:</b>\n"
        "• Бот для интернет-магазина (Telegram)\n"
        "• Бот поддержки для сервиса такси (VK)\n"
        "• Образовательный бот (Discord)\n\n"
        "<b>🌐 Сайты:</b>\n"
        "• Корпоративный сайт для строительной компании\n"
        "• Интернет-магазин электроники\n"
        "• Лендинг для онлайн-курсов\n\n"
        "<b>🎨 Дизайн:</b>\n"
        "• UI/UX для финтех приложения\n"
        "• Брендбук для сети кофеен\n\n"
        "🌐 <b>Наш сайт:</b> https://gog.su/CodeForge_IT"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()

@router.callback_query(F.data == "contact")
async def contact(callback: CallbackQuery):
    text = (
        "📞 <b>Свяжитесь с нами:</b>\n\n"
        "🌐 Сайт: https://gog.su/CodeForge_IT\n"
        "📢 Telegram канал: https://t.me/CodeForge_IT\n"
        "👥 ВКонтакте: https://vk.ru/codeforge_it\n"
        "📧 Email: codeforge@list.ru\n\n"
        "<b>Режим работы:</b>\n"
        "Понедельник: 15:00 - 23:00\n"
        "Вторник: 14:00 - 23:00\n"
        "Среда: 16:00 - 23:00\n"
        "Четверг: 14:00 - 23:00\n"
        "Пятница: 14:00 - 23:00\n"
        "Суббота: 9:00 - 23:00\n"
        "Воскресенье: выходной (берём заказы)"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()

# Админ-панель
@router.callback_query(F.data == "admin_panel")
async def admin_panel(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещен!", show_alert=True)
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="📦 Новые заказы", callback_data="admin_new_orders")],
        [InlineKeyboardButton(text="⏳ Заказы в обработке", callback_data="admin_in_progress")],
        [InlineKeyboardButton(text="✅ Выполненные заказы", callback_data="admin_completed")],
        [InlineKeyboardButton(text="📜 Вся история", callback_data="admin_all_orders")],
        [InlineKeyboardButton(text="🔙 Выход", callback_data="main_menu")]
    ])
    
    await callback.message.edit_text(
        "⚙️ <b>Админ-панель</b>\n\n"
        "Выберите действие:",
        reply_markup=keyboard
    )
    await callback.answer()

@router.callback_query(F.data == "admin_stats")
async def admin_stats(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещен!", show_alert=True)
        return
    
    total_users, new_orders, in_progress = get_statistics()
    
    text = (
        f"📊 <b>Статистика</b>\n\n"
        f"👥 Всего пользователей: <b>{total_users}</b>\n"
        f"🆕 Новых заказов: <b>{new_orders}</b>\n"
        f"⚙️ Заказов в работе: <b>{in_progress}</b>"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()

@router.callback_query(F.data == "admin_new_orders")
async def admin_new_orders(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещен!", show_alert=True)
        return
    
    orders = get_orders_by_status('новый')
    
    if not orders:
        text = "📭 Новых заказов нет."
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")]
        ])
        await callback.message.edit_text(text, reply_markup=keyboard)
        return
    
    keyboard_buttons = []
    for order in orders:
        order_id, user_id, category, order_date = order
        keyboard_buttons.append([
            InlineKeyboardButton(text=f"Заказ #{order_id} ({category})", 
                               callback_data=f"admin_order_{order_id}")
        ])
    
    keyboard_buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    
    await callback.message.edit_text(
        f"📦 <b>Новые заказы ({len(orders)}):</b>\n\n"
        "Выберите заказ для просмотра:",
        reply_markup=keyboard
    )
    await callback.answer()

@router.callback_query(F.data.startswith("admin_order_"))
async def admin_order_detail(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещен!", show_alert=True)
        return
    
    order_id = int(callback.data.split("_")[2])
    order = get_order_details(order_id)
    
    if not order:
        await callback.answer("Заказ не найден!", show_alert=True)
        return
    
    order_dict = {
        'order_id': order[0],
        'user_id': order[1],
        'order_date': order[2],
        'category': order[3],
        'platform': order[4],
        'description': order[5],
        'currency': order[6],
        'budget': order[7],
        'status': order[8],
        'admin_comment': order[9],
        'username': order[10],
        'full_name': order[11]
    }
    
    text = (
        f"📋 <b>Заказ #{order_dict['order_id']}</b>\n\n"
        f"👤 <b>Клиент:</b>\n"
        f"ID: <code>{order_dict['user_id']}</code>\n"
        f"Username: @{order_dict['username'] if order_dict['username'] else 'нет'}\n"
        f"Имя: {order_dict['full_name']}\n\n"
        f"📅 Дата заказа: {order_dict['order_date']}\n"
        f"🏷️ Категория: {order_dict['category']}\n"
        f"📱 Платформа: {order_dict['platform']}\n"
        f"💰 Валюта: {order_dict['currency']}\n"
        f"💵 Бюджет: {order_dict['budget']}\n"
        f"📝 Описание: {order_dict['description']}\n\n"
        f"📊 Статус: <b>{order_dict['status']}</b>"
    )
    
    if order_dict['admin_comment']:
        text += f"\n💬 Комментарий админа: {order_dict['admin_comment']}"
    
    keyboard_buttons = []
    if order_dict['status'] == 'новый':
        keyboard_buttons.append([
            InlineKeyboardButton(text="✅ Принять заказ", 
                               callback_data=f"admin_accept_{order_id}"),
            InlineKeyboardButton(text="❌ Отклонить", 
                               callback_data=f"admin_reject_{order_id}")
        ])
    elif order_dict['status'] in ['в обработке', 'принят']:
        keyboard_buttons.append([
            InlineKeyboardButton(text="✅ Выполнен", 
                               callback_data=f"admin_complete_{order_id}"),
            InlineKeyboardButton(text="❌ Не выполнен", 
                               callback_data=f"admin_failed_{order_id}")
        ])
    
    keyboard_buttons.append([InlineKeyboardButton(text="🔙 Назад", 
                                                callback_data="admin_new_orders")])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()

@router.callback_query(F.data.startswith("admin_accept_"))
async def admin_accept_order(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещен!", show_alert=True)
        return
    
    order_id = int(callback.data.split("_")[2])
    update_order_status(order_id, 'в обработке')
    
    # Уведомление пользователя
    order = get_order_details(order_id)
    if order:
        user_id = order[1]
        try:
            await bot.send_message(
                user_id,
                f"✅ Ваш заказ #{order_id} принят в работу!\n"
                f"С вами свяжется администратор в ближайшее время."
            )
        except:
            pass
    
    await callback.answer("✅ Заказ принят в работу!", show_alert=True)
    await admin_new_orders(callback)

@router.callback_query(F.data.startswith("admin_reject_"))
async def admin_reject_order(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещен!", show_alert=True)
        return
    
    order_id = int(callback.data.split("_")[2])
    await state.set_state(AdminStates.waiting_for_rejection_reason)
    await state.update_data(order_id=order_id)
    
    await callback.message.edit_text(
        "📝 <b>Отклонение заказа</b>\n\n"
        "Введите причину отклонения заказа (или отправьте 'пропустить' для пропуска):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔙 Отмена", callback_data=f"admin_order_{order_id}")
        ]])
    )
    await callback.answer()

@router.message(AdminStates.waiting_for_rejection_reason)
async def process_rejection_reason(message: Message, state: FSMContext):
    data = await state.get_data()
    order_id = data['order_id']
    reason = message.text if message.text != 'пропустить' else "Не указана"
    
    update_order_status(order_id, 'отклонен', reason)
    
    # Уведомление пользователя
    order = get_order_details(order_id)
    if order:
        user_id = order[1]
        try:
            await bot.send_message(
                user_id,
                f"❌ К сожалению, ваш заказ #{order_id} отклонен.\n"
                f"Причина: {reason}"
            )
        except:
            pass
    
    await message.answer(f"✅ Заказ #{order_id} отклонен с причиной: {reason}")
    await state.clear()
    
    # Возвращаемся к списку заказов
    await admin_new_orders_handler(message)

async def admin_new_orders_handler(message: Message):
    await admin_new_orders(CallbackQuery(
        message=message,
        data="admin_new_orders",
        id="temp",
        chat_instance="temp",
        from_user=message.from_user
    ))

@router.callback_query(F.data == "admin_in_progress")
async def admin_in_progress(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещен!", show_alert=True)
        return
    
    orders_in_progress = get_orders_by_status('в обработке')
    orders_accepted = get_orders_by_status('принят')
    orders = orders_in_progress + orders_accepted
    
    if not orders:
        text = "⏳ Заказов в обработке нет."
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")]
        ])
        await callback.message.edit_text(text, reply_markup=keyboard)
        return
    
    keyboard_buttons = []
    for order in orders:
        order_id, user_id, category, order_date = order
        keyboard_buttons.append([
            InlineKeyboardButton(text=f"Заказ #{order_id} ({category})", 
                               callback_data=f"admin_order_{order_id}")
        ])
    
    keyboard_buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    
    await callback.message.edit_text(
        f"⏳ <b>Заказы в обработке ({len(orders)}):</b>\n\n"
        "Выберите заказ для просмотра:",
        reply_markup=keyboard
    )
    await callback.answer()

@router.callback_query(F.data.startswith("admin_complete_"))
async def admin_complete_order(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещен!", show_alert=True)
        return
    
    order_id = int(callback.data.split("_")[2])
    update_order_status(order_id, 'выполнен')
    
    # Уведомление пользователя
    order = get_order_details(order_id)
    if order:
        user_id = order[1]
        try:
            await bot.send_message(
                user_id,
                f"🎉 Ваш заказ #{order_id} выполнен!\n"
                f"Спасибо, что выбрали нас! Оплата по договоренности."
            )
        except:
            pass
    
    await callback.answer("✅ Заказ отмечен как выполненный!", show_alert=True)
    await admin_in_progress(callback)

@router.callback_query(F.data.startswith("admin_failed_"))
async def admin_failed_order(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещен!", show_alert=True)
        return
    
    order_id = int(callback.data.split("_")[2])
    update_order_status(order_id, 'не выполнен')
    
    # Уведомление пользователя
    order = get_order_details(order_id)
    if order:
        user_id = order[1]
        try:
            await bot.send_message(
                user_id,
                f"Ваш заказ #{order_id} отмечен как невыполненный (клиент отказался)."
            )
        except:
            pass
    
    await callback.answer("❌ Заказ отмечен как не выполненный!", show_alert=True)
    await admin_in_progress(callback)

@router.callback_query(F.data == "admin_completed")
async def admin_completed(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещен!", show_alert=True)
        return
    
    orders = get_orders_by_status('выполнен')
    
    if not orders:
        text = "✅ Выполненных заказов нет."
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")]
        ])
        await callback.message.edit_text(text, reply_markup=keyboard)
        return
    
    text = "✅ <b>Выполненные заказы:</b>\n\n"
    for order in orders[:20]:  # Ограничиваем показ
        order_id, user_id, category, order_date = order
        text += f"<b>Заказ #{order_id}</b>\n"
        text += f"Категория: {category}\n"
        text += f"Клиент ID: {user_id}\n"
        text += f"Дата: {order_date}\n"
        text += "─" * 20 + "\n"
    
    if len(orders) > 20:
        text += f"\n... и еще {len(orders) - 20} заказов"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()

@router.callback_query(F.data == "admin_all_orders")
async def admin_all_orders(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещен!", show_alert=True)
        return
    
    orders = get_all_orders()
    
    if not orders:
        text = "📭 Заказов нет."
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")]
        ])
        await callback.message.edit_text(text, reply_markup=keyboard)
        return
    
    # Группируем по статусам
    status_groups = {}
    for order in orders:
        status = order[8]  # status field
        if status not in status_groups:
            status_groups[status] = 0
        status_groups[status] += 1
    
    text = "📜 <b>Вся история заказов</b>\n\n"
    text += f"📊 Всего заказов: <b>{len(orders)}</b>\n\n"
    text += "<b>Статистика по статусам:</b>\n"
    
    for status, count in status_groups.items():
        text += f"• {status}: <b>{count}</b>\n"
    
    text += "\nДля просмотра деталей конкретного заказа используйте разделы выше."
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()

# Обработка заказа
@router.callback_query(F.data.startswith("category_"))
async def process_category(callback: CallbackQuery, state: FSMContext):
    category = callback.data.split("_")[1]
    
    if category == "chatbot":
        category_text = "Чат-бот"
        await state.set_state(OrderStates.waiting_for_platform)
        await state.update_data(category=category_text)
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Telegram", callback_data="platform_telegram")],
            [InlineKeyboardButton(text="VK", callback_data="platform_vk")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="order_project")]
        ])
        
        await callback.message.edit_text(
            "🤖 <b>Вы выбрали: Чат-бот</b>\n\n"
            "Теперь выберите платформу:",
            reply_markup=keyboard
        )
    else:
        if category == "website":
            category_text = "Сайт"
            platform_text = "Не указано"
        else:  # other
            category_text = "Другое"
            platform_text = "Не указано"
        
        await state.set_state(OrderStates.waiting_for_description)
        await state.update_data(category=category_text, platform=platform_text)
        
        await callback.message.edit_text(
            f"✅ <b>Вы выбрали: {category_text}</b>\n\n"
            "Теперь опишите ваш проект. Чем подробнее вы опишете задачу, тем точнее мы сможем оценить стоимость и сроки выполнения.\n\n"
            "<i>Отправьте текстовое сообщение с описанием проекта...</i>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🔙 Назад", callback_data="order_project")
            ]])
        )
    
    await callback.answer()

@router.callback_query(F.data.startswith("platform_"))
async def process_platform(callback: CallbackQuery, state: FSMContext):
    platform = callback.data.split("_")[1]
    
    if platform == "telegram":
        platform_text = "Telegram"
    else:  # vk
        platform_text = "VK"
    
    await state.set_state(OrderStates.waiting_for_description)
    await state.update_data(platform=platform_text)
    
    await callback.message.edit_text(
        f"✅ <b>Вы выбрали платформу: {platform_text}</b>\n\n"
        "Теперь опишите ваш проект. Чем подробнее вы опишете задачу, тем точнее мы сможем оценить стоимость и сроки выполнения.\n\n"
        "<i>Отправьте текстовое сообщение с описанием проекта...</i>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔙 Назад", callback_data="category_chatbot")
        ]])
    )
    await callback.answer()

@router.message(OrderStates.waiting_for_description)
async def process_description(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("Пожалуйста, отправьте текстовое описание проекта.")
        return
    
    if len(message.text) < 10:
        await message.answer("Описание слишком короткое. Пожалуйста, опишите проект подробнее.")
        return
    
    await state.set_state(OrderStates.waiting_for_currency)
    await state.update_data(description=message.text)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="₽ Русские рубли", callback_data="currency_rub")],
        [InlineKeyboardButton(text="Br Белорусские рубли", callback_data="currency_byn")],
        [InlineKeyboardButton(text="¥ Китайские юани", callback_data="currency_cny")],
        [InlineKeyboardButton(text="€ Евро", callback_data="currency_eur")],
        [InlineKeyboardButton(text="₸ Тенге", callback_data="currency_kzt")],
        [InlineKeyboardButton(text="$ Доллар", callback_data="currency_usd")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_category")]
    ])
    
    await message.answer(
        "✅ <b>Описание сохранено!</b>\n\n"
        "Теперь выберите валюту для бюджета:",
        reply_markup=keyboard
    )

@router.callback_query(F.data == "back_to_category")
async def back_to_category(callback: CallbackQuery, state: FSMContext):
    await state.set_state(OrderStates.waiting_for_category)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🤖 Чат-бот", callback_data="category_chatbot")],
        [InlineKeyboardButton(text="🌐 Сайт", callback_data="category_website")],
        [InlineKeyboardButton(text="💼 Другое", callback_data="category_other")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")]
    ])
    
    await callback.message.edit_text(
        "🛠️ <b>Заказ проекта</b>\n\n"
        "Выберите категорию проекта:",
        reply_markup=keyboard
    )
    await callback.answer()

@router.callback_query(F.data.startswith("currency_"))
async def process_currency(callback: CallbackQuery, state: FSMContext):
    currency_map = {
        'rub': 'Русские рубли (₽)',
        'byn': 'Белорусские рубли (Br)',
        'cny': 'Китайские юани (¥)',
        'eur': 'Евро (€)',
        'kzt': 'Тенге (₸)',
        'usd': 'Доллар ($)'
    }
    
    currency_code = callback.data.split("_")[1]
    currency_text = currency_map.get(currency_code, 'Не указано')
    
    await state.set_state(OrderStates.waiting_for_budget)
    await state.update_data(currency=currency_text)
    
    await callback.message.edit_text(
        f"✅ <b>Валюта: {currency_text}</b>\n\n"
        "Теперь укажите примерный бюджет для вашего проекта.\n\n"
        "<i>Отправьте текстовое сообщение с бюджетом (например: 5000-10000 руб, 100-200$, договорная и т.д.)...</i>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_currency")
        ]])
    )
    await callback.answer()

@router.callback_query(F.data == "back_to_currency")
async def back_to_currency(callback: CallbackQuery, state: FSMContext):
    await state.set_state(OrderStates.waiting_for_currency)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="₽ Русские рубли", callback_data="currency_rub")],
        [InlineKeyboardButton(text="Br Белорусские рубли", callback_data="currency_byn")],
        [InlineKeyboardButton(text="¥ Китайские юани", callback_data="currency_cny")],
        [InlineKeyboardButton(text="€ Евро", callback_data="currency_eur")],
        [InlineKeyboardButton(text="₸ Тенге", callback_data="currency_kzt")],
        [InlineKeyboardButton(text="$ Доллар", callback_data="currency_usd")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_description")]
    ])
    
    await callback.message.edit_text(
        "Выберите валюту для бюджета:",
        reply_markup=keyboard
    )
    await callback.answer()

@router.callback_query(F.data == "back_to_description")
async def back_to_description(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    
    await state.set_state(OrderStates.waiting_for_description)
    
    await callback.message.edit_text(
        "Теперь опишите ваш проект. Чем подробнее вы опишете задачу, тем точнее мы сможем оценить стоимость и сроки выполнения.\n\n"
        "<i>Отправьте текстовое сообщение с описанием проекта...</i>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔙 Назад", callback_data="order_project")
        ]])
    )
    await callback.answer()

@router.message(OrderStates.waiting_for_budget)
async def process_budget(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("Пожалуйста, укажите бюджет.")
        return
    
    await state.set_state(OrderStates.waiting_for_confirmation)
    await state.update_data(budget=message.text)
    
    data = await state.get_data()
    
    summary = (
        f"📋 <b>Сводка заказа</b>\n\n"
        f"<b>Категория:</b> {data.get('category', 'Не указано')}\n"
        f"<b>Платформа:</b> {data.get('platform', 'Не указано')}\n"
        f"<b>Описание:</b> {data.get('description', 'Не указано')}\n"
        f"<b>Валюта:</b> {data.get('currency', 'Не указано')}\n"
        f"<b>Бюджет:</b> {data.get('budget', 'Не указано')}\n\n"
        f"<i>Всё верно?</i>"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm_order"),
            InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_order")
        ],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_budget")]
    ])
    
    await message.answer(summary, reply_markup=keyboard)

@router.callback_query(F.data == "back_to_budget")
async def back_to_budget(callback: CallbackQuery, state: FSMContext):
    await state.set_state(OrderStates.waiting_for_budget)
    
    data = await state.get_data()
    currency = data.get('currency', '')
    
    currency_map_reverse = {
        'Русские рубли (₽)': 'currency_rub',
        'Белорусские рубли (Br)': 'currency_byn',
        'Китайские юани (¥)': 'currency_cny',
        'Евро (€)': 'currency_eur',
        'Тенге (₸)': 'currency_kzt',
        'Доллар ($)': 'currency_usd'
    }
    
    back_data = currency_map_reverse.get(currency, 'back_to_currency')
    
    await callback.message.edit_text(
        "Теперь укажите примерный бюджет для вашего проекта.\n\n"
        "<i>Отправьте текстовое сообщение с бюджетом (например: 5000-10000 руб, 100-200$, договорная и т.д.)...</i>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔙 Назад", callback_data=back_data)
        ]])
    )
    await callback.answer()

@router.callback_query(F.data == "confirm_order")
async def confirm_order(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    data = await state.get_data()
    
    # Создаем заказ в БД
    order_id = create_order(
        user_id=user_id,
        category=data.get('category'),
        platform=data.get('platform', 'Не указано'),
        description=data.get('description'),
        currency=data.get('currency'),
        budget=data.get('budget')
    )
    
    # Получаем информацию о пользователе
    user_info = get_user_info(user_id)
    username = user_info[0] if user_info else "не указан"
    
    # Отправляем уведомление админам
    admins = [1514979458]  # Основной админ
    
    admin_message = (
        f"🆕 <b>НОВЫЙ ЗАКАЗ #{order_id}</b>\n\n"
        f"👤 <b>Клиент:</b>\n"
        f"ID: <code>{user_id}</code>\n"
        f"Username: @{username}\n\n"
        f"📋 <b>Детали заказа:</b>\n"
        f"Категория: {data.get('category')}\n"
        f"Платформа: {data.get('platform', 'Не указано')}\n"
        f"Валюта: {data.get('currency')}\n"
        f"Бюджет: {data.get('budget')}\n\n"
        f"📝 <b>Описание:</b>\n{data.get('description')}\n\n"
        f"📅 Дата: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    
    for admin_id in admins:
        try:
            await bot.send_message(admin_id, admin_message)
        except:
            pass
    
    await callback.message.edit_text(
        f"🎉 <b>Заказ #{order_id} успешно оформлен!</b>\n\n"
        "Наш администратор получил уведомление и свяжется с вами в ближайшее время.\n\n"
        "Спасибо за выбор CodeForge! 💻",
        reply_markup=get_main_menu(user_id)
    )
    
    await state.clear()
    await callback.answer()

@router.callback_query(F.data == "cancel_order")
async def cancel_order(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    user_id = callback.from_user.id
    
    await callback.message.edit_text(
        "❌ <b>Создание заказа отменено</b>\n\n"
        "Если передумаете - всегда можно создать новый заказ!",
        reply_markup=get_main_menu(user_id)
    )
    await callback.answer()

# Обработка кнопки "Назад" в главное меню
@router.callback_query(F.data == "main_menu")
async def back_to_main_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    user_id = callback.from_user.id
    
    await callback.message.edit_text(
        "👋 Добро пожаловать!\n\n"
        "Выберите действие в меню ниже:",
        reply_markup=get_main_menu(user_id)
    )
    await callback.answer()

# Запуск бота
async def main():
    # Инициализация БД
    init_db()
    
    # Запуск бота
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())