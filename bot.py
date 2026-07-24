import os
import json
import asyncio
from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import Command
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardButton, 
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InputMediaPhoto
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

TOKEN = "8924615859:AAE0LqHClZasq1Zii768_N9DWFlVvgynmyI"
ADMIN_IDS = [8633592767]
MANAGER_CHAT_ID = -1004301495465  # Чат/админ, куда летят заявки на ремонт и фото

DB_FILE = "cards_db.json"

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

# FSM Состояния для записи на ремонт
class AppointmentStates(StatesGroup):
    entering_plate = State()
    entering_vin = State()
    entering_brand_model = State()
    entering_reason = State()

# FSM Состояния для оценки по фото
class PhotoEstimateStates(StatesGroup):
    entering_plate = State()
    entering_vin = State()
    entering_brand_model = State()
    uploading_photos = State()

# FSM Состояния для добавления авто из карточки лояльности
class AddCarStates(StatesGroup):
    plate = State()
    vin = State()
    brand_model = State()


bot = Bot(token=TOKEN)
dp = Dispatcher()
router = Router()

# Главные плитки бота
def get_main_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="💳 Карта лояльности", callback_data="loyalty_card"))
    builder.row(InlineKeyboardButton(text="📅 Записаться на ремонт", callback_data="book_repair"))
    builder.row(InlineKeyboardButton(text="📸 Оценить по фото", callback_data="photo_estimate"))
    builder.row(InlineKeyboardButton(text="📞 Контактная информация", callback_data="contact_info"))
    return builder.as_markup()

# Обработчик команды /start
@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
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
            "Для активации вашей персональной карты лояльности и начисления приветственных **750 баллов**, пожалуйста, поделитесь вашим номером телефона с помощью кнопки ниже 👇",
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
        db[user_id] = {"turnover": 0.0, "bonus_balance": 750.0, "active_refs": 0, "invited_by": None, "first_visit_done": False, "cars": []}
    
    db[user_id]["phone"] = phone
    save_db(db)
    
    await message.answer(
        "✅ Телефон успешно сохранен! Ваша карта лояльности активна.",
        reply_markup=ReplyKeyboardRemove()
    )
    await message.answer("Главное меню:", reply_markup=get_main_keyboard())


# === 4. КОНТАКТНАЯ ИНФОРМАЦИЯ ===
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


# === 1. КАРТА ЛОЯЛЬНОСТИ ===
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
async def back_to_menu_callback(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Главное меню:", reply_markup=get_main_keyboard())
    await callback.answer()

@router.callback_query(F.data == "add_car_to_garage")
async def add_car_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AddCarStates.plate)
    await callback.message.answer("Введите номер машины:")
    await callback.answer()

@router.message(AddCarStates.plate)
async def add_car_plate(message: Message, state: FSMContext):
    await state.update_data(plate=message.text)
    await state.set_state(AddCarStates.vin)
    await message.answer("Введите вин номер машины:")

@router.message(AddCarStates.vin)
async def add_car_vin(message: Message, state: FSMContext):
    await state.update_data(vin=message.text)
    await state.set_state(AddCarStates.brand_model)
    await message.answer("Введите марку и модель:")

@router.message(AddCarStates.brand_model)
async def add_car_finish(message: Message, state: FSMContext):
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
    await message.answer("✅ Автомобиль успешно добавлен в базу!", reply_markup=get_main_keyboard())


# === 2. ЗАПИСАТЬСЯ НА РЕМОНТ ===
@router.callback_query(F.data == "book_repair")
async def book_repair_start(callback: CallbackQuery, state: FSMContext):
    db = load_db()
    user_id = str(callback.from_user.id)
    user_cars = db.get(user_id, {}).get("cars", [])
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="а. Новая машина", callback_data="repair_car_new"))
    if user_cars:
        builder.row(InlineKeyboardButton(text="б. Выбрать машину из гаража", callback_data="repair_car_garage"))
    builder.row(InlineKeyboardButton(text="◀️ Отмена", callback_data="back_to_menu"))
    
    await callback.message.edit_text(
        "📅 **Записаться на ремонт**\n\nВыберите вариант:", 
        parse_mode="Markdown", 
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# Ветка А: Новая машина
@router.callback_query(F.data == "repair_car_new")
async def repair_car_new(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AppointmentStates.entering_plate)
    await callback.message.answer("1. Введите номер машины:")
    await callback.answer()

@router.message(AppointmentStates.entering_plate)
async def repair_entered_plate(message: Message, state: FSMContext):
    await state.update_data(plate=message.text)
    await state.set_state(AppointmentStates.entering_vin)
    await message.answer("2. Введите вин номер машины:")

@router.message(AppointmentStates.entering_vin)
async def repair_entered_vin(message: Message, state: FSMContext):
    await state.update_data(vin=message.text)
    await state.set_state(AppointmentStates.entering_brand_model)
    await message.answer("3. Введите марку и модель:")

@router.message(AppointmentStates.entering_brand_model)
async def repair_entered_brand(message: Message, state: FSMContext):
    await state.update_data(brand=message.text, is_new=True)
    await state.set_state(AppointmentStates.entering_reason)
    await message.answer("4. Введите причину обращения:")

# Ветка Б: Выбрать из гаража
@router.callback_query(F.data == "repair_car_garage")
async def repair_car_garage(callback: CallbackQuery, state: FSMContext):
    db = load_db()
    user_id = str(callback.from_user.id)
    cars = db.get(user_id, {}).get("cars", [])
    
    builder = InlineKeyboardBuilder()
    for idx, car in enumerate(cars):
        builder.row(InlineKeyboardButton(
            text=f"{car.get('brand')} (номер: {car.get('plate')})", 
            callback_data=f"sel_rep_car_{idx}"
        ))
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="book_repair"))
    
    await callback.message.edit_text("1. Выберите машину из гаража:", reply_markup=builder.as_markup())
    await callback.answer()

@router.callback_query(F.data.startswith("sel_rep_car_"))
async def repair_selected_garage_car(callback: CallbackQuery, state: FSMContext):
    car_idx = int(callback.data.split("_")[-1])
    db = load_db()
    user_id = str(callback.from_user.id)
    car = db.get(user_id, {}).get("cars", [])[car_idx]
    
    await state.update_data(car=car, is_new=False)
    await state.set_state(AppointmentStates.entering_reason)
    await callback.message.answer("2. Введите причину обращения:")
    await callback.answer()

@router.message(AppointmentStates.entering_reason)
async def repair_entered_reason(message: Message, state: FSMContext):
    data = await state.get_data()
    reason = message.text
    user_id = str(message.from_user.id)
    db = load_db()
    user = db.get(user_id, {})
    phone = user.get("phone", "Не указан")
    
    if data.get("is_new"):
        car_info = f"Марка/модель: {data.get('brand')}\nНомер: {data.get('plate')}\nVIN: {data.get('vin')}"
        if "cars" not in user:
            user["cars"] = []
        user["cars"].append({
            "brand": data.get("brand"),
            "plate": data.get("plate"),
            "vin": data.get("vin")
        })
        save_db(db)
    else:
        car = data.get("car", {})
        car_info = f"Марка/модель: {car.get('brand')}\nНомер: {car.get('plate')}\nVIN: {car.get('vin')}"
        
    text = (
        "📅 **Запись на ремонт**\n\n"
        f"👤 Клиент ID: `{user_id}`\n"
        f"📞 Телефон: {phone}\n\n"
        "🚘 **Автомобиль:**\n"
        f"{car_info}\n\n"
        f"💬 **Причина обращения:**\n{reason}"
    )
    
    try:
        await bot.send_message(MANAGER_CHAT_ID, text, parse_mode="Markdown")
    except Exception as e:
        print(f"Ошибка отправки в чат менеджеров: {e}")
        
    await state.clear()
    await message.answer("✅ Ваша заявка успешно отправлена!", reply_markup=get_main_keyboard())


# === 3. ОЦЕНИТЬ ПО ФОТО ===
@router.callback_query(F.data == "photo_estimate")
async def photo_estimate_start(callback: CallbackQuery, state: FSMContext):
    db = load_db()
    user_id = str(callback.from_user.id)
    user_cars = db.get(user_id, {}).get("cars", [])
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="а. Новая машина", callback_data="photo_car_new"))
    if user_cars:
        builder.row(InlineKeyboardButton(text="б. Выбрать машину из гаража", callback_data="photo_car_garage"))
    builder.row(InlineKeyboardButton(text="◀️ Отмена", callback_data="back_to_menu"))
    
    await callback.message.edit_text(
        "📸 **Оценить по фото**\n\nВыберите вариант:", 
        parse_mode="Markdown", 
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# Ветка А: Новая машина
@router.callback_query(F.data == "photo_car_new")
async def photo_car_new(callback: CallbackQuery, state: FSMContext):
    await state.set_state(PhotoEstimateStates.entering_plate)
    await callback.message.answer("1. Введите номер машины:")
    await callback.answer()

@router.message(PhotoEstimateStates.entering_plate)
async def photo_entered_plate(message: Message, state: FSMContext):
    await state.update_data(plate=message.text)
    await state.set_state(PhotoEstimateStates.entering_vin)
    await message.answer("2. Введите вин номер машины:")

@router.message(PhotoEstimateStates.entering_vin)
async def photo_entered_vin(message: Message, state: FSMContext):
    await state.update_data(vin=message.text)
    await state.set_state(PhotoEstimateStates.entering_brand_model)
    await message.answer("3. Введите марку и модель:")

@router.message(PhotoEstimateStates.entering_brand_model)
async def photo_entered_brand(message: Message, state: FSMContext):
    await state.update_data(brand=message.text, is_new=True)
    await state.set_state(PhotoEstimateStates.uploading_photos)
    await message.answer("4. Отправьте фотографии (можно несколько). После отправки всех фото нажмите кнопку ниже 👇", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="✅ Готово, отправить")]], resize_keyboard=True, one_time_keyboard=True))

# Ветка Б: Выбрать из гаража
@router.callback_query(F.data == "photo_car_garage")
async def photo_car_garage(callback: CallbackQuery, state: FSMContext):
    db = load_db()
    user_id = str(callback.from_user.id)
    cars = db.get(user_id, {}).get("cars", [])
    
    builder = InlineKeyboardBuilder()
    for idx, car in enumerate(cars):
        builder.row(InlineKeyboardButton(
            text=f"{car.get('brand')} (номер: {car.get('plate')})", 
            callback_data=f"sel_ph_car_{idx}"
        ))
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="photo_estimate"))
    
    await callback.message.edit_text("1. Выберите машину из гаража:", reply_markup=builder.as_markup())
    await callback.answer()

@router.callback_query(F.data.startswith("sel_ph_car_"))
async def photo_selected_garage_car(callback: CallbackQuery, state: FSMContext):
    car_idx = int(callback.data.split("_")[-1])
    db = load_db()
    user_id = str(callback.from_user.id)
    car = db.get(user_id, {}).get("cars", [])[car_idx]
    
    await state.update_data(car=car, is_new=False)
    await state.set_state(PhotoEstimateStates.uploading_photos)
    await message.answer("2. Отправьте фотографии (можно несколько). После отправки всех фото нажмите кнопку ниже 👇", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="✅ Готово, отправить")]], resize_keyboard=True, one_time_keyboard=True))
    await callback.answer()

@router.message(PhotoEstimateStates.uploading_photos, F.photo)
async def handle_photo_upload(message: Message, state: FSMContext):
    data = await state.get_data()
    photos = data.get("photos", [])
    photos.append(message.photo[-1].file_id)
    await state.update_data(photos=photos)
    await message.answer(f"📸 Фото принято ({len(photos)} шт.). Отправьте еще или нажмите «✅ Готово, отправить».")

@router.message(PhotoEstimateStates.uploading_photos, F.text == "✅ Готово, отправить")
async def finalize_photo_estimate(message: Message, state: FSMContext):
    data = await state.get_data()
    photos = data.get("photos", [])
    
    if not photos:
        return await message.answer("Вы не отправили ни одной фотографии!")
        
    user_id = str(message.from_user.id)
    db = load_db()
    user = db.get(user_id, {})
    phone = user.get("phone", "Не указан")
    
    if data.get("is_new"):
        car_info = f"Марка/модель: {data.get('brand')}\nНомер: {data.get('plate')}\nVIN: {data.get('vin')}"
        if "cars" not in user:
            user["cars"] = []
        user["cars"].append({
            "brand": data.get("brand"),
            "plate": data.get("plate"),
            "vin": data.get("vin")
        })
        save_db(db)
    else:
        car = data.get("car", {})
        car_info = f"Марка/модель: {car.get('brand')}\nНомер: {car.get('plate')}\nVIN: {car.get('vin')}"

    caption = (
        "📸 **Оценка по фото**\n\n"
        f"👤 Клиент ID: `{user_id}`\n"
        f"📞 Телефон: {phone}\n\n"
        "🚘 **Автомобиль:**\n"
        f"{car_info}"
    )
    
    media_group = [InputMediaPhoto(media=photos[0], caption=caption, parse_mode="Markdown")]
    for p_id in photos[1:]:
        media_group.append(InputMediaPhoto(media=p_id))
        
    try:
        await bot.send_media_group(chat_id=MANAGER_CHAT_ID, media=media_group)
    except Exception as e:
        print(f"Ошибка отправки альбома в чат менеджеров: {e}")
        
    await state.clear()
    await message.answer("✅ Фотографии успешно отправлены менеджерам!", reply_markup=get_main_keyboard())


# === АДМИНСКАЯ КОМАНДА ФИКСАЦИИ ВИЗИТА ===
@router.message(Command("visit"))
async def admin_register_visit(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return await message.answer("Нет прав администратора.")
    
    args = message.text.split()
    if len(args) < 3:
        return await message.answer("Формат: `/visit ID_клиента сумма да/нет`", parse_mode="Markdown")
    
    client_id = args[1]
    amount = float(args[2])
    is_first_visit = args[3].lower() in ['да', 'yes', '1', 'true'] if len(args) > 3 else False
    
    db = load_db()
    if client_id not in db:
        db[client_id] = {"phone": "Касса", "turnover": 0.0, "bonus_balance": 0.0, "active_refs": 0, "invited_by": None, "first_visit_done": False, "cars": []}
    
    client = db[client_id]
    
    if is_first_visit and not client.get("first_visit_done", False):
        client["first_visit_done"] = True
        referrer_id = client.get("invited_by")
        if referrer_id and referrer_id in db:
            ref_bonus = min(amount * 0.10, 5000.0)
            db[referrer_id]["bonus_balance"] += ref_bonus
            db[referrer_id]["active_refs"] = db[referrer_id].get("active_refs", 0) + 1
            try:
                await bot.send_message(
                    int(referrer_id), 
                    f"🎉 Ваш друг совершил первый визит!\n"
                    f"🎁 Вам начислено 10%: *{ref_bonus:,.0f} баллов*.", 
                    parse_mode="Markdown"
                )
            except:
                pass

    client["turnover"] += amount
    personal_rate, _, _ = get_personal_cashback_rate(client["turnover"])
    client_cashback = amount * (personal_rate / 100.0)
    client["bonus_balance"] += client_cashback

    referrer_id = client.get("invited_by")
    if referrer_id and referrer_id in db:
        ref_owner = db[referrer_id]
        passive_rate = get_referral_passive_rate(ref_owner.get("active_refs", 0))
        if passive_rate > 0:
            passive_bonus = amount * (passive_rate / 100.0)
            ref_owner["bonus_balance"] += passive_bonus
            try:
                await bot.send_message(
                    int(referrer_id),
                    f"📈 Вам начислен пассивный кэшбэк ({passive_rate}%): *{passive_bonus:,.0f} баллов*.",
                    parse_mode="Markdown"
                )
            except:
                pass

    save_db(db)
    await message.answer(
        f"✅ Визит зарегистрирован!\n"
        f"👤 Клиент: {client_id} | Сумма: {amount:,.0f} ₽\n"
        f"💵 Кэшбэк клиенту ({personal_rate}%): {client_cashback:,.0f} баллов"
    )

@router.message(Command("burn"))
async def admin_burn_bonuses(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    args = message.text.split()
    if len(args) < 3:
        return await message.answer("Формат: `/burn ID сумма`")
    client_id = args[1]
    burn_amount = float(args[2])
    db = load_db()
    if client_id not in db or db[client_id]["bonus_balance"] < burn_amount:
        return await message.answer("❌ Недостаточно баллов.")
    db[client_id]["bonus_balance"] -= burn_amount
    save_db(db)
    await message.answer(f"✅ Успешно списано {burn_amount} баллов у {client_id}.")


async def main():
    dp.include_router(router)
    print("Бот запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
