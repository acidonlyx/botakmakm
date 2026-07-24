import os
import json
import logging
from aiohttp import web
from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import Command
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardButton, 
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InputMediaPhoto,
    WebAppData
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.state import State, StatesGroup

TOKEN = "8924615859:AAE0LqHClZasq1Zii768_N9DWFlVvgynmyI"
ADMIN_IDS = [8633592767]
MANAGER_CHAT_ID = 8633592767  # Чат/админ, куда летят заявки на ремонт и фото

# Укажите реальный URL вашего развернутого Mini App (или тестовый домен)
WEB_APP_URL = "# Укажите реальный URL вашего развернутого Mini App на Render
WEB_APP_URL = "https://botakmakm.onrender.com/index.html"" 

DB_FILE = "cards_db.json"

def load_db():
    if not os.path.exists(DB_FILE):
        return {}
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Ошибка загрузки базы данных: {e}")
        return {}

def save_db(db):
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(db, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logging.error(f"Ошибка сохранения базы данных: {e}")

# 1. Личный кэшбэк от годового оборота
def get_personal_cashback_rate(turnover):
    if turnover >= 1000000:
        return 7, 1000000, "Максимальный личный кэшбэк (7%)!"
    elif turnover >= 500000:
        return 5, 1000000, "Осталось до 7%: " + f"{1000000 - turnover:,.0f} баллов"
    elif turnover >= 300000:
        return 4, 500000, "Осталось до 5%: " + f"{500000 - turnover:,.0f} баллов"
    elif turnover >= 200000:
        return 3, 300000, "Осталось до 4%: " + f"{300000 - turnover:,.0f} баллов"
    elif turnover >= 100000:
        return 2, 200000, "Осталось до 3%: " + f"{200000 - turnover:,.0f} баллов"
    else:
        return 1, 100000, "Осталось до 2%: " + f"{100000 - turnover:,.0f} баллов"

# 2. Реферальный процент (пассивный доход с чеков друзей)
def get_referral_passive_rate(active_refs):
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

# Персональная скидка
def calculate_discount(turnover):
    if turnover >= 1000000:
        return 20
    elif turnover >= 600000:
        return 15
    elif turnover >= 250000:
        return 10
    elif turnover >= 100000:
        return 5
    else:
        return 0

# FSM Состояния для бота
class AppointmentStates(StatesGroup):
    entering_plate = State()
    entering_vin = State()
    entering_brand_model = State()
    entering_reason = State()

class PhotoEstimateStates(StatesGroup):
    entering_plate = State()
    entering_vin = State()
    entering_brand_model = State()
    uploading_photos = State()

class AddCarStates(StatesGroup):
    plate = State()
    vin = State()
    brand_model = State()


bot = Bot(token=TOKEN)
dp = Dispatcher()
router = Router()

def get_main_keyboard():
    builder = InlineKeyboardBuilder()
    # Кнопка открытия Mini App (Личный кабинет с плитками)
    builder.row(InlineKeyboardButton(text="📱 Личный кабинет (App)", web_app=web_app_url_obj()))
    builder.row(InlineKeyboardButton(text="💳 Карта лояльности", callback_data="loyalty_card"))
    builder.row(InlineKeyboardButton(text="📅 Записаться на ремонт", callback_data="book_repair"))
    builder.row(InlineKeyboardButton(text="📸 Оценить по фото", callback_data="photo_estimate"))
    builder.row(InlineKeyboardButton(text="📞 Контактная информация", callback_data="contact_info"))
    return builder.as_markup()

def web_app_url_obj():
    from aiogram.types import WebAppInfo
    return WebAppInfo(url=WEB_APP_URL)

@router.message(Command("start"))
async def cmd_start(message: Message, state):
    await state.clear()
    user_id = str(message.from_user.id)
    args = message.text.split()
    
    db = load_db()
    
    if user_id not in db:
        referrer_id = args[1] if len(args) > 1 and args[1] != user_id else None
        
        db[user_id] = {
            "phone": None,
            "turnover": 0.0,
            "bonus_balance": 750.0,
            "active_refs": 0,
            "invited_by": referrer_id,
            "first_visit_done": False,
            "cars": []
        }
        save_db(db)

    user_data = db.get(user_id, {})
    if not user_data.get("phone") or user_data.get("phone") == "Не указан":
        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="📱 Поделиться номером телефона", request_contact=True)]
            ],
            resize_keyboard=True,
            one_time_keyboard=True
        )
        await message.answer(
            "👋 Добро пожаловать в **АКМ Авто**!\n\n"
            "Для активации вашей персональной карты лояльности и начисления приветственных **750 баллов**, пожалуйста, поделитесь вашим номером телефона 👇",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    else:
        await message.answer(
            "👋 Рады снова видеть вас в **АКМ Авто**!\n\n"
            "Выберите интересующий вас раздел:",
            reply_markup=get_main_keyboard(),
            parse_mode="Markdown"
        )

@router.message(F.contact)
async def handle_contact(message: Message):
    user_id = str(message.from_user.id)
    phone = message.contact.phone_number
    
    db = load_db()
    if user_id not in db:
        db[user_id] = {
            "phone": phone,
            "turnover": 0.0,
            "bonus_balance": 750.0,
            "active_refs": 0,
            "invited_by": None,
            "first_visit_done": False,
            "cars": []
        }
    else:
        db[user_id]["phone"] = phone
        
    save_db(db)
    
    await message.answer(
        "✅ Телефон успешно сохранен! Ваша карта лояльности активна.",
        reply_markup=ReplyKeyboardRemove()
    )
    await message.answer("Главное меню:", reply_markup=get_main_keyboard())


# Обработка данных, прилетающих из Mini App через tg.sendData()
@router.message(F.web_app_data)
async def handle_web_app_data(message: Message):
    try:
        data = json.loads(message.web_app_data.data)
        action = data.get("action")
        user_id = str(message.from_user.id)
        db = load_db()

        if action == "repair":
            car_info = data.get("car")
            reason = data.get("reason")
            phone = db.get(user_id, {}).get("phone", "Не указан")

            text = (
                "📅 **Новая заявка на ремонт из Mini App**\n\n"
                f"👤 Клиент ID: `{user_id}`\n"
                f"📞 Телефон: {phone}\n"
                f"🚘 Автомобиль: {car_info}\n"
                f"💬 Описание: {reason}"
            )
            await bot.send_message(MANAGER_CHAT_ID, text, parse_mode="Markdown")
            await message.answer("✅ Ваша заявка на ремонт успешно отправлена менеджерам!", reply_markup=get_main_keyboard())
            
    except Exception as e:
        logging.error(f"Ошибка обработки WebApp данных: {e}")
        await message.answer("❌ Произошла ошибка при отправке данных.", reply_markup=get_main_keyboard())


# === КОНТАКТЫ ===
@router.callback_query(F.data == "contact_info")
async def contact_info_callback(callback: CallbackQuery):
    text = (
        "📞 **Контактная информация АКМ Авто**\n\n"
        "📱 Телефон: +7 (921) 950-01-10\n"
        "📍 Адрес: Рубежная ул., 2Л\n"
        "⏰ График работы: с 10:00 до 20:00"
    )
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="◀️ Назад в меню", callback_data="back_to_menu"))
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=builder.as_markup())
    await callback.answer()


# === КАРТА ЛОЯЛЬНОСТИ (Дублирующий текстовый интерфейс) ===
@router.callback_query(F.data == "loyalty_card")
async def loyalty_card_callback(callback: CallbackQuery):
    user_id = str(callback.from_user.id)
    db = load_db()
    user = db.get(user_id, {"bonus_balance": 0, "turnover": 0, "active_refs": 0, "cars": []})
    
    balance = user.get("bonus_balance", 0)
    discount = calculate_discount(user.get("turnover", 0))
    cashback_rate, _, _ = get_personal_cashback_rate(user.get("turnover", 0))
    ref_count = user.get("active_refs", 0)
    ref_rate = get_referral_passive_rate(ref_count)
    ref_link = f"https://t.me/akmautospb_bot?start={user_id}"
    
    cars = user.get("cars", [])
    cars_text = ""
    if cars:
        for idx, car in enumerate(cars, 1):
            cars_text += f"\n  🚗 Авто {idx}: {car.get('brand')} | Гос. номер: {car.get('plate')} | VIN: {car.get('vin')}"
    else:
        cars_text = "\n  _У вас пока нет добавленных автомобилей в гараже._"

    text = (
        "💳 **Карта лояльности АКМ Авто**\n\n"
        "📊 **Информация по карте:**\n"
        f"1️⃣ Кол-во баллов: **{balance:,.0f}**\n"
        f"2️⃣ Скидка: **{discount}%**\n"
        f"3️⃣ Процент кэшбэка: **{cashback_rate}%**\n\n"
        f"🚘 **Гараж автомобилей:**{cars_text}\n\n"
        "-------------------------------------\n"
        "🎁 **Реферальная программа:**\n"
        f"1️⃣ Количество рефералов: **{ref_count} чел.**\n"
        f"2️⃣ Процент кэшбэка от затрат рефералов: **{ref_rate}%**\n\n"
        f"🔗 Ваша реферальная ссылка:\n`{ref_link}`"
    )
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="➕ Добавить автомобиль", callback_data="add_car_to_garage"))
    builder.row(InlineKeyboardButton(text="◀️ Назад в меню", callback_data="back_to_menu"))
    
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=builder.as_markup())
    await callback.answer()

@router.callback_query(F.data == "back_to_menu")
async def back_to_menu_callback(callback: CallbackQuery, state):
    await state.clear()
    await callback.message.edit_text("Главное меню:", reply_markup=get_main_keyboard())
    await callback.answer()

@router.callback_query(F.data == "add_car_to_garage")
async def add_car_start(callback: CallbackQuery, state):
    await state.set_state(AddCarStates.plate)
    await callback.message.answer("Введите гос. номер машины (например, А000АА178):")
    await callback.answer()

@router.message(AddCarStates.plate)
async def add_car_plate(message: Message, state):
    await state.update_data(plate=message.text)
    await state.set_state(AddCarStates.vin)
    await message.answer("Введите VIN-номер машины (17 символов):")

@router.message(AddCarStates.vin)
async def add_car_vin(message: Message, state):
    await state.update_data(vin=message.text)
    await state.set_state(AddCarStates.brand_model)
    await message.answer("Введите марку и модель автомобиля (например, Kia Sportage):")

@router.message(AddCarStates.brand_model)
async def add_car_finish(message: Message, state):
    data = await state.get_data()
    user_id = str(message.from_user.id)
    
    db = load_db()
    if user_id not in db:
        db[user_id] = {"cars": []}
    if "cars" not in db[user_id]:
        db[user_id]["cars"] = []
        
    new_car = {
        "plate": data.get("plate"),
        "vin": data.get("vin"),
        "brand": message.text
    }
    db[user_id]["cars"].append(new_car)
    save_db(db)
    
    await state.clear()
    await message.answer("✅ Автомобиль успешно добавлен в ваш гараж!", reply_markup=get_main_keyboard())


# === ЗАПИСЬ НА РЕМОНТ И ОЦЕНКА ПО ФОТО ===
@router.callback_query(F.data == "book_repair")
async def book_repair_start(callback: CallbackQuery, state):
    await state.set_state(AppointmentStates.entering_plate)
    await callback.message.answer("📅 Введите гос. номер автомобиля для записи на ремонт:")
    await callback.answer()

@router.message(AppointmentStates.entering_plate)
async def repair_plate(message: Message, state):
    await state.update_data(plate=message.text)
    await state.set_state(AppointmentStates.entering_reason)
    await message.answer("Опишите причину обращения или какая требуется услуга:")

@router.message(AppointmentStates.entering_reason)
async def repair_reason(message: Message, state):
    data = await state.get_data()
    user_id = str(message.from_user.id)
    db = load_db()
    user = db.get(user_id, {})
    phone = user.get("phone", "Не указан")
    
    text = (
        "📅 **Новая заявка на ремонт с бота**\n\n"
        f"👤 Клиент ID: `{user_id}`\n"
        f"📞 Телефон: {phone}\n"
        f"🚘 Гос. номер: {data.get('plate')}\n"
        f"💬 Описание: {message.text}"
    )
    try:
        await bot.send_message(MANAGER_CHAT_ID, text, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Не удалось отправить заявку менеджеру: {e}")
        
    await state.clear()
    await message.answer("✅ Ваша заявка успешно отправлена менеджерам! Скоро с вами свяжутся.", reply_markup=get_main_keyboard())

@router.callback_query(F.data == "photo_estimate")
async def photo_est_start(callback: CallbackQuery, state):
    await state.set_state(PhotoEstimateStates.uploading_photos)
    await state.update_data(photos=[])
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="✅ Готово (отправить)")]],
        resize_keyboard=True
    )
    await callback.message.answer(
        "📸 **Оценка стоимости ремонта по фото**\n\n"
        "Пожалуйста, отправьте одно или несколько фото повреждений. Когда закончите, нажмите кнопку «✅ Готово (отправить)» внизу.",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    await callback.answer()

@router.message(PhotoEstimateStates.uploading_photos, F.photo)
async def get_ph(message: Message, state):
    data = await state.get_data()
    data["photos"].append(message.photo[-1].file_id)
    await state.update_data(photos=data["photos"])
    await message.answer(f"📸 Фото принято ({len(data['photos'])} шт.). Отправьте еще или нажмите «✅ Готово (отправить)».")

@router.message(PhotoEstimateStates.uploading_photos, F.text == "✅ Готово (отправить)")
async def finish_ph(message: Message, state):
    data = await state.get_data()
    photos = data.get("photos", [])
    if not photos:
        await message.answer("Вы не прикрепили ни одной фотографии!")
        return
    
    user_id = str(message.from_user.id)
    db = load_db()
    phone = db.get(user_id, {}).get("phone", "Не указан")
    
    caption = f"📸 **Заявка на оценку по фото**\n👤 ID клиента: `{user_id}`\n📞 Телефон: {phone}"
    
    try:
        if len(photos) == 1:
            await bot.send_photo(MANAGER_CHAT_ID, photo=photos[0], caption=caption, parse_mode="Markdown")
        else:
            media = [InputMediaPhoto(media=photos[0], caption=caption, parse_mode="Markdown")]
            for p in photos[1:]:
                media.append(InputMediaPhoto(media=p))
            await bot.send_media_group(MANAGER_CHAT_ID, media)
    except Exception as e:
        logging.error(f"Ошибка отправки медиагруппы менеджеру: {e}")

    await state.clear()
    await message.answer("✅ Ваши фотографии отправлены в кузовной цех! Оценщик свяжется с вами в ближайшее время.", reply_markup=get_main_keyboard())


# ==========================================
# === WEB API ДЛЯ ADMIN.HTML (AIOHTTP) ===
# ==========================================

async def api_search_clients(request):
    admin_id = int(request.query.get("admin_id", 0))
    if admin_id not in ADMIN_IDS:
        return web.json_response({"success": False, "error": "Unauthorized"}, status=403)
    
    query = request.query.get("query", "").lower()
    db = load_db()
    results = []
    
    for uid, udata in db.items():
        phone = str(udata.get("phone", ""))
        cars = udata.get("cars", [])
        car_str = ", ".join([f"{c.get('brand')} ({c.get('plate')})" for c in cars]) or "Нет машин"
        
        if (query in phone.lower() or 
            query in uid.lower() or 
            any(query in c.get('plate', '').lower() or query in c.get('vin', '').lower() for c in cars)):
            
            results.append({
                "user_id": uid,
                "phone": phone,
                "bonus_balance": udata.get("bonus_balance", 0),
                "turnover": udata.get("turnover", 0),
                "car_info": car_str
            })
            
    return web.json_response({"success": True, "users": results})

async def api_add_transaction(request):
    try:
        data = await request.json()
        admin_id = int(data.get("admin_id", 0))
        if admin_id not in ADMIN_IDS:
            return web.json_response({"success": False, "error": "Unauthorized"}, status=403)
            
        client_id = str(data.get("user_id"))
        amount = float(data.get("amount", 0))
        is_first_visit = bool(data.get("is_first_visit", False))
        
        db = load_db()
        if client_id not in db:
            return web.json_response({"success": False, "error": "Client not found"})
            
        client = db[client_id]
        
        # 1. Реферальный бонус за первый визит (10%, макс 5000)
        if is_first_visit and not client.get("first_visit_done", False):
            client["first_visit_done"] = True
            referrer_id = client.get("invited_by")
            if referrer_id and referrer_id in db:
                ref_bonus = min(amount * 0.10, 5000.0)
                db[referrer_id]["bonus_balance"] = db[referrer_id].get("bonus_balance", 0) + ref_bonus
                db[referrer_id]["active_refs"] = db[referrer_id].get("active_refs", 0) + 1
                try:
                    await bot.send_message(
                        int(referrer_id), 
                        f"🎉 Ваш приглашенный друг совершил первый визит!\n🎁 Вам начислен бонус: *{ref_bonus:,.0f} баллов*.", 
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    logging.error(f"Не удалось уведомить реферера: {e}")

        # 2. Личный кэшбэк
        client["turnover"] = client.get("turnover", 0.0) + amount
        personal_rate, _, _ = get_personal_cashback_rate(client["turnover"])
        client_cashback = amount * (personal_rate / 100.0)
        client["bonus_balance"] = client.get("bonus_balance", 0.0) + client_cashback

        # 3. Пассивный кэшбэк рефереру с обычных визитов
        referrer_id = client.get("invited_by")
        if referrer_id and referrer_id in db and not is_first_visit:
            ref_owner = db[referrer_id]
            passive_rate = get_referral_passive_rate(ref_owner.get("active_refs", 0))
            if passive_rate > 0:
                passive_bonus = amount * (passive_rate / 100.0)
                ref_owner["bonus_balance"] += passive_bonus
                try:
                    await bot.send_message(
                        int(referrer_id), 
                        f"📈 Вам начислен пассивный кэшбэк с чека друга: *{passive_bonus:,.0f} баллов*.", 
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    logging.error(f"Не удалось уведомить реферера о пассивном кэшбэке: {e}")

        save_db(db)
        
        # Уведомляем клиента о визите и кэшбэке
        try:
            await bot.send_message(
                int(client_id), 
                f"🎉 Внесен визит на сумму **{amount:,.0f} ₽**!\n💵 Начислен кэшбэк: *{client_cashback:,.0f} баллов*.\n📊 Общий баланс баллов: *{client['bonus_balance']:,.0f}*.", 
                parse_mode="Markdown"
            )
        except Exception as e:
            logging.error(f"Не удалось уведомить клиента о транзакции: {e}")

        return web.json_response({"success": True})
    except Exception as e:
        logging.error(f"Ошибка в api_add_transaction: {e}")
        return web.json_response({"success": False, "error": str(e)}, status=500)

async def api_burn_bonuses(request):
    try:
        data = await request.json()
        admin_id = int(data.get("admin_id", 0))
        if admin_id not in ADMIN_IDS:
            return web.json_response({"success": False, "error": "Unauthorized"}, status=403)
            
        client_id = str(data.get("user_id"))
        amount = float(data.get("amount", 0))
        
        db = load_db()
        if client_id not in db:
            return web.json_response({"success": False, "error": "Client not found"})
            
        client = db[client_id]
        if client.get("bonus_balance", 0) < amount:
            return web.json_response({"success": False, "error": "Недостаточно баллов на балансе у клиента"})
            
        client["bonus_balance"] -= amount
        save_db(db)
        
        try:
            await bot.send_message(
                int(client_id), 
                f"➖ С вашего баланса списано: *{amount:,.0f} баллов*.\n📊 Остаток баланса: *{client['bonus_balance']:,.0f} баллов*.", 
                parse_mode="Markdown"
            )
        except Exception as e:
            logging.error(f"Не удалось уведомить клиента о списании: {e}")

        return web.json_response({"success": True})
    except Exception as e:
        logging.error(f"Ошибка в api_burn_bonuses: {e}")
        return web.json_response({"success": False, "error": str(e)}, status=500)

async def setup_web_server():
    app = web.Application()
    
    @web.middleware
    async def cors_middleware(request, handler):
        if request.method == "OPTIONS":
            return web.Response(headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type",
                "Access-Control-Allow-Methods": "POST, GET, OPTIONS"
            })
        response = await handler(request)
        response.headers["Access-Control-Allow-Origin"] = "*"
        return response

    app.middlewares.append(cors_middleware)
    
    app.router.add_get("/api/admin/search", api_search_clients)
    app.router.add_post("/api/admin/add_transaction", api_add_transaction)
    app.router.add_post("/api/admin/burn_bonuses", api_burn_bonuses)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8000)
    await site.start()
    logging.info("Веб-сервер API успешно запущен на порту 8000.")


async def main():
    dp.include_router(router)
    await setup_web_server()
    logging.info("Telegram-бот запущен и ожидает сообщения...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    import asyncio
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Бот остановлен пользователем.")
