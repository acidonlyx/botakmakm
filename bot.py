import os
import json
import asyncio
from aiohttp import web
from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import Command
from aiogram.types import Message, WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton

# === НАСТРОЙКИ ===
TOKEN = "7949432655:AAHx-1u7W07rK9bI09V7NlG0WlW_UvE529I"  # Ваш токен бота
WEBAPP_URL = "https://botakmakm.onrender.com/index.html"  # Ссылка на ваш Render-сервер
ADMIN_IDS = [8633592767]  # Telegram ID администраторов / кассиров для управления визитами

DB_FILE = "cards_db.json"

# === РАБОТА С БАЗОЙ ДАННЫХ (JSON) ===
def load_db():
    if not os.path.exists(DB_FILE):
        return {}
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_db(db):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=4)

# === ЛОГИКА СКИДОК И КЭШБЭКА ===
def calculate_discount(turnover):
    if turnover >= 1000000:
        return 20, "4 Уровень", 1000000, "Максимальный уровень достигнут!"
    elif turnover >= 600000:
        return 15, "3 Уровень", 1000000, "Осталось до 4 ур.: " + f"{1000000 - turnover:,} ₽"
    elif turnover >= 250000:
        return 10, "2 Уровень", 600000, "Осталось до 3 ур.: " + f"{600000 - turnover:,} ₽"
    elif turnover >= 100000:
        return 5, "1 Уровень", 250000, "Осталось до 2 ур.: " + f"{250000 - turnover:,} ₽"
    else:
        return 0, "Начальный", 100000, "Осталось до 1 ур.: " + f"{100000 - turnover:,} ₽"

def get_ref_rate(active_refs):
    if active_refs >= 10:
        return 5
    elif active_refs >= 5:
        return 3
    elif active_refs >= 3:
        return 2
    elif active_refs >= 1:
        return 1
    else:
        return 0

# === ИНИЦИАЛИЗАЦИЯ БОТА И РОУТЕРА ===
bot = Bot(token=TOKEN)
dp = Dispatcher()
router = Router()

# Главное меню
def get_main_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Карта лояльности", web_app=WebAppInfo(url=WEBAPP_URL))],
        [InlineKeyboardButton(text="🎁 Реферальная программа", callback_data="ref_menu")],
        [InlineKeyboardButton(text="📞 Связаться с мастером", callback_data="contact")]
    ])

# Команда /start с обработкой рефералов (антиабуз)
@router.message(Command("start"))
async def cmd_start(message: Message):
    user_id = str(message.from_user.id)
    args = message.text.split()
    
    db = load_db()
    
    # Если пользователя еще нет в базе — создаем карточку
    if user_id not in db:
        db[user_id] = {
            "phone": "Не указан",
            "turnover": 0.0,
            "bonus_balance": 0.0,
            "active_refs": 0,
            "invited_by": None,
            "first_visit_done": False
        }
        
        # Проверяем реферальную ссылку (если перешел по приглашению)
        if len(args) > 1:
            referrer_id = args[1]
            if referrer_id != user_id and referrer_id in db:
                db[user_id]["invited_by"] = referrer_id
                # Новому пользователю фиксируем приветственный бонус на первый визит
                db[user_id]["bonus_balance"] += 750.0 
                
        save_db(db)

    welcome_text = (
        "👋 Добро пожаловать в **АКМ Авто**!\n\n"
        "Ваша виртуальная карта лояльности и реферальный бонус (750 ₽ на первый визит) уже активированы.\n"
        "Нажмите кнопку ниже, чтобы открыть карту и управлять бонусами 👇"
    )
    await message.answer(welcome_text, reply_markup=get_main_keyboard(), parse_mode="Markdown")

@router.callback_query(F.data == "ref_menu")
async def ref_menu_callback(callback: Message):
    user_id = str(callback.from_user.id)
    db = load_db()
    user = db.get(user_id, {"active_refs": 0, "bonus_balance": 0})
    
    current_rate = get_ref_rate(user.get("active_refs", 0))
    ref_link = f"https://t.me/akmautospb_bot?start={user_id}"
    
    text = (
        "🎁 **Реферальная программа АКМ Авто**\n\n"
        "1️⃣ Друг получает **750 ₽** на первый визит.\n"
        "2️⃣ Вы получаете **10%** от стоимости его первого визита (до 5 000 бонусов) после того, как он приедет в сервис!\n\n"
        f"👥 Приглашено друзей (с визитами): **{user.get('active_refs', 0)} чел.**\n"
        f"💵 Ваш текущий кэшбэк с визитов друзей: **{current_rate}%**\n\n"
        f"🔗 Ваша личная ссылка для приглашений:\n`{ref_link}`"
    )
    await callback.message.answer(text, parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "contact")
async def contact_callback(callback: Message):
    await callback.message.answer("📞 Телефон главного сервиса: +7 (999) 000-00-00\n📍 Адрес: ул. Автомобильная, 1")
    await callback.answer()

# === АДМИНСКИЕ КОМАНДЫ ДЛЯ СТО ===

# Регистрация визита: /visit <ID_клиента> <сумма> <да/нет (первый визит)>
@router.message(Command("visit"))
async def admin_register_visit(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return await message.answer("У вас нет прав администратора.")
    
    args = message.text.split()
    if len(args) < 3:
        return await message.answer("⚠️ Формат: `/visit ID_клиента сумма да_или_нет`", parse_mode="Markdown")
    
    client_id = args[1]
    try:
        amount = float(args[2])
    except ValueError:
        return await message.answer("⚠️ Ошибка: сумма должна быть числом.")
        
    is_first_visit = args[3].lower() in ['да', 'yes', '1', 'true'] if len(args) > 3 else False
    
    db = load_db()
    if client_id not in db:
        db[client_id] = {"phone": "Касса", "turnover": 0.0, "bonus_balance": 0.0, "active_refs": 0, "invited_by": None, "first_visit_done": False}
    
    user = db[client_id]
    
    # Обработка антиабуза при первом визите
    if is_first_visit and not user.get("first_visit_done", False):
        user["first_visit_done"] = True
        referrer_id = user.get("invited_by")
        if referrer_id and referrer_id in db:
            ref_bonus = min(amount * 0.10, 5000.0)
            db[referrer_id]["bonus_balance"] += ref_bonus
            db[referrer_id]["active_refs"] = db[referrer_id].get("active_refs", 0) + 1
            
            try:
                await bot.send_message(
                    int(referrer_id), 
                    f"🎉 Ваш друг совершил первый визит на сумму {amount:,.0f} ₽!\n"
                    f"🎁 Вам начислено 10% кэшбэка: *{ref_bonus:,.0f} бонусов*.", 
                    parse_mode="Markdown"
                )
            except:
                pass

    # Увеличиваем оборот клиента
    user["turnover"] += amount
    
    # Начисляем кэшбэк клиенту согласно уровню его рефералов
    ref_rate = get_ref_rate(user.get("active_refs", 0))
    client_cashback = amount * (ref_rate / 100.0)
    user["bonus_balance"] += client_cashback

    save_db(db)

    await message.answer(
        f"✅ Визит успешно зафиксирован!\n"
        f"👤 Клиент ID: {client_id}\n"
        f"💰 Чек: {amount:,.0f} ₽\n"
        f"🏷 Первый визит: {'Да' if is_first_visit else 'Нет'}\n"
        f"💵 Начислено кэшбэка клиенту ({ref_rate}%): *{client_cashback:,.0f} бонусов*",
        parse_mode="Markdown"
    )

# Списание бонусов: /burn <ID_клиента> <сумма>
@router.message(Command("burn"))
async def admin_burn_bonuses(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    args = message.text.split()
    if len(args) < 3:
        return await message.answer("⚠️ Формат: `/burn ID_клиента сумма`", parse_mode="Markdown")
    
    client_id = args[1]
    burn_amount = float(args[2])
    
    db = load_db()
    if client_id not in db or db[client_id]["bonus_balance"] < burn_amount:
        return await message.answer("❌ Ошибка: у клиента недостаточно бонусов.")
    
    db[client_id]["bonus_balance"] -= burn_amount
    save_db(db)
    
    await message.answer(f"✅ Успешно списано {burn_amount} бонусов у клиента {client_id}.\nОстаток: {db[client_id]['bonus_balance']} бонусов.")


# === WEB SERVER ДЛЯ MINI APP (API) ===
async def handle_api_user_data(request):
    user_id = request.rel_url.query.get('user_id')
    db = load_db()
    
    if not user_id or user_id not in db:
        # Данные по умолчанию для нового/ненайденного пользователя
        default_data = {
            "phone": "Не указан",
            "turnover": 0,
            "discount": 0,
            "level_name": "Начальный",
            "ref_count": 0,
            "bonus_balance": 750, # Приветственный бонус
            "ref_rate": 0,
            "max_target": 100000,
            "next_text": "Осталось накопить до 1 ур.: 100 000 ₽"
        }
        return web.json_response(default_data)
    
    user = db[user_id]
    discount, level_name, max_target, next_text = calculate_discount(user["turnover"])
    ref_rate = get_ref_rate(user.get("active_refs", 0))
    
    response_data = {
        "phone": user.get("phone", "Не указан"),
        "turnover": user["turnover"],
        "discount": discount,
        "level_name": level_name,
        "ref_count": user.get("active_refs", 0),
        "bonus_balance": user["bonus_balance"],
        "ref_rate": ref_rate,
        "max_target": max_target,
        "next_text": next_text
    }
    return web.json_response(response_data)


# === ЗАПУСК СЕРВЕРА И БОТА ===
async def main():
    dp.include_router(router)
    
    # Настройка aiohttp сервера для Render
    app = web.Application()
    app.router.add_get('/api/user_data', handle_api_user_data)
    app.router.add_static('/', path='./webapp', name='webapp')
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    
    # Сначала запускаем веб-сервер, чтобы Render зафиксировал порт
    await site.start()
    print(f"Веб-сервер запущен на порту {port}")
    
    # Параллельно запускаем бота
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
