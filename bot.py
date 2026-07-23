import asyncio
import logging
import json
import os
from aiohttp import web
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart, Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
    WebAppInfo
)
from aiogram.utils.media_group import MediaGroupBuilder

TOKEN = "8924615859:AAFBt-yx9fFQmPM7JZ8k6Dp4jPrCQmlThXo"
ADMIN_CHAT_ID = -1004301495465
ADMIN_IDS = [8633592767]

router = Router()
DB_FILE = "cards_db.json"

def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_db():
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(cards_db, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logging.error(f"Не удалось сохранить базу данных: {e}")

cards_db = load_db()
phone_auth_state = {}

def get_discount_level(turnover: float):
    if turnover >= 500000:
        return 4, 20, "4 уровень (Максимальный)", 500000
    elif turnover >= 350000:
        return 3, 15, "3 уровень", 500000
    elif turnover >= 150000:
        return 2, 10, "2 уровень", 350000
    elif turnover >= 75000:
        return 1, 5, "1 уровень", 150000
    else:
        return 0, 0, "Начальный (до 1 уровня)", 75000

def get_referral_cashback_rate(referrals_count: int):
    if referrals_count >= 10:
        return 7
    elif referrals_count >= 5:
        return 5
    elif referrals_count >= 1:
        return 3
    else:
        return 1

class BookingForm(StatesGroup):
    car_brand = State()
    car_model = State()
    car_vin = State()
    phone = State()
    full_name = State()
    issue_description = State()

class PhotoEstimateForm(StatesGroup):
    car_brand = State()
    car_model = State()
    car_vin = State()
    phone = State()
    full_name = State()
    photos = State()

album_data = {}

# В главной клавиатуре кнопка открывает Mini App
# ВНИМАНИЕ: Вместо 'https://yourdomain.com/webapp/index.html' вам нужно указать адрес, 
# где будет доступен ваш сайт (например, через ngrok для тестов, либо реальный хостинг).
WEBAPP_URL = "https://botakmakm.onrender.com/index.html"

main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🚗 Записаться в сервис"), KeyboardButton(text="💳 Моя карта и бонусы", web_app=WebAppInfo(url=WEBAPP_URL))],
        [KeyboardButton(text="📸 Оценить ремонт по фото"), KeyboardButton(text="📞 Связаться с мастером")]
    ],
    resize_keyboard=True
)

cancel_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="❌ Отменить заявку")]],
    resize_keyboard=True
)

phone_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📱 Поделиться номером телефона", request_contact=True)],
        [KeyboardButton(text="❌ Отменить")]
    ],
    resize_keyboard=True,
    one_time_keyboard=True
)

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, command: CommandObject):
    await state.clear()
    user = message.from_user
    args = command.args

    if args and args.isdigit():
        referrer_id = int(args)
        if referrer_id != user.id:
            for p, info in cards_db.items():
                if info.get("user_id") == referrer_id:
                    already_referred = any(user.id in info.get("referrals_list", []) for info in cards_db.values())
                    if not already_referred:
                        if "referrals_list" not in info:
                            info["referrals_list"] = []
                        if user.id not in info["referrals_list"]:
                            info["referrals_list"].append(user.id)
                            info["bonus_balance"] = info.get("bonus_balance", 0.0) + 300.0
                            save_db()
                            try:
                                await message.bot.send_message(
                                    chat_id=referrer_id,
                                    text=f"🎉 По вашей ссылке зарегистрировался друг! Вам начислено **300 бонусов**! 💰",
                                    parse_mode="Markdown"
                                )
                            except Exception:
                                pass
                    break

    welcome_text = (
        f"Здравствуйте, {user.first_name}! 👋\n\n"
        "Вас приветствует официальный бот сети автосервисов **АКМ Авто** (Санкт-Петербург, Рубежная ул., 2Л).\n\n"
        "Нажмите кнопку **«💳 Моя карта и бонусы»**, чтобы открыть персональное приложение с вашей скидкой и реферальной системой:"
    )
    await message.answer(welcome_text, reply_markup=main_menu, parse_mode="Markdown")

@router.message(Command("add"))
async def admin_add_turnover(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ У вас нет прав.")
        return

    args = message.text.split()
    if len(args) != 3:
        await message.answer("⚠️ Формат: `/add [телефон] [сумма]`", parse_mode="Markdown")
        return
    
    search_phone = args[1].strip().replace("+", "")
    try:
        amount = float(args[2])
    except ValueError:
        await message.answer("⚠️ Сумма должна быть числом.")
        return
    
    found_key = None
    for db_phone in cards_db.keys():
        if db_phone.strip().replace("+", "") == search_phone:
            found_key = db_phone
            break

    if not found_key:
        await message.answer(f"❌ Карточка `{search_phone}` не найдена!", parse_mode="Markdown")
        return
    
    cards_db[found_key]["turnover"] += amount
    new_turnover = cards_db[found_key]["turnover"]
    
    client_user_id = cards_db[found_key].get("user_id")
    if client_user_id:
        for p, info in cards_db.items():
            if client_user_id in info.get("referrals_list", []):
                ref_count = len(info.get("referrals_list", []))
                cb_rate = get_referral_cashback_rate(ref_count)
                cashback_earned = amount * (cb_rate / 100.0)
                info["bonus_balance"] = info.get("bonus_balance", 0.0) + cashback_earned
                save_db()
                try:
                    await message.bot.send_message(
                        chat_id=info["user_id"],
                        text=f"💸 Вам поступил реферальный кэшбэк **{int(cashback_earned)} руб.** ({cb_rate}% от друга)!",
                        parse_mode="Markdown"
                    )
                except Exception:
                    pass
                break

    save_db()
    _, discount, level_name, _ = get_discount_level(new_turnover)
    
    await message.answer(
        f"✅ **Обороты обновлены!**\n📱 Тел: `{found_key}`\n📊 Оборот: **{int(new_turnover)} руб.**\n⭐ Уровень: **{level_name} ({discount}%)**",
        parse_mode="Markdown"
    )

@router.message(F.text == "❌ Отменить заявку")
async def cancel_handler(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Действие отменено.", reply_markup=main_menu)

@router.message(F.text == "❌ Отменить")
async def cancel_phone_handler(message: Message):
    await message.answer("Действие отменено.", reply_markup=main_menu)

@router.message(F.contact)
async def process_contact(message: Message, state: FSMContext):
    user_id = message.from_user.id
    phone = message.contact.phone_number.strip().replace("+", "")

    if phone not in cards_db:
        cards_db[phone] = {
            "user_id": user_id,
            "name": message.from_user.full_name,
            "turnover": 0.0,
            "bonus_balance": 0.0,
            "referrals_list": []
        }
    else:
        cards_db[phone]["user_id"] = user_id
    save_db()
    await message.answer("✅ Телефон успешно сохранен! Теперь откройте приложение кнопкой ниже.", reply_markup=main_menu)

@router.message(F.text == "🚗 Записаться в сервис")
async def start_booking(message: Message, state: FSMContext):
    await state.set_state(BookingForm.car_brand)
    await message.answer("🚗 Укажите марку вашего автомобиля:", reply_markup=cancel_kb)

@router.message(BookingForm.car_brand)
async def process_booking_brand(message: Message, state: FSMContext):
    await state.update_data(car_brand=message.text)
    await state.set_state(BookingForm.car_model)
    await message.answer("Укажите модель автомобиля:")

@router.message(BookingForm.car_model)
async def process_booking_model(message: Message, state: FSMContext):
    await state.update_data(car_model=message.text)
    await state.set_state(BookingForm.car_vin)
    await message.answer("Введите VIN-номер или гос. номер:")

@router.message(BookingForm.car_vin)
async def process_booking_vin(message: Message, state: FSMContext):
    await state.update_data(car_vin=message.text)
    await state.set_state(BookingForm.phone)
    await message.answer("Введите контактный телефон для связи:")

@router.message(BookingForm.phone)
async def process_booking_phone(message: Message, state: FSMContext):
    phone = message.text.strip().replace("+", "")
    await state.update_data(phone=phone)
    await state.set_state(BookingForm.full_name)
    await message.answer("Укажите ваши ФИО:")

@router.message(BookingForm.full_name)
async def process_booking_fullname(message: Message, state: FSMContext):
    await state.update_data(full_name=message.text)
    await state.set_state(BookingForm.issue_description)
    await message.answer("📝 Опишите причину обращения:")

@router.message(BookingForm.issue_description)
async def process_booking_description(message: Message, state: FSMContext, bot: Bot):
    await state.update_data(issue_description=message.text)
    data = await state.get_data()
    
    admin_message = (
        f"🔔 **Новая заявка!**\n📱 `{data['phone']}`\n🚘 *{data['car_brand']} {data['car_model']}*\n"
        f"🔢 VIN: `{data['car_vin']}`\n👤 *{data['full_name']}*\n📋 _{data['issue_description']}_"
    )
    try:
        await bot.send_message(chat_id=ADMIN_CHAT_ID, text=admin_message, parse_mode="Markdown")
    except Exception:
        pass
    
    await message.answer("✅ Заявка принята! Мастер свяжется с вами.", reply_markup=main_menu)
    await state.clear()

@router.message(F.text == "📸 Оценить ремонт по фото")
async def start_photo_estimate(message: Message, state: FSMContext):
    await state.set_state(PhotoEstimateForm.car_brand)
    await message.answer("📸 Укажите марку автомобиля:", reply_markup=cancel_kb)

@router.message(PhotoEstimateForm.car_brand)
async def process_photo_brand(message: Message, state: FSMContext):
    await state.update_data(car_brand=message.text)
    await state.set_state(PhotoEstimateForm.car_model)
    await message.answer("Укажите модель:")

@router.message(PhotoEstimateForm.car_model)
async def process_photo_model(message: Message, state: FSMContext):
    await state.update_data(car_model=message.text)
    await state.set_state(PhotoEstimateForm.car_vin)
    await message.answer("Введите VIN-номер или гос. номер:")

@router.message(PhotoEstimateForm.car_vin)
async def process_photo_vin(message: Message, state: FSMContext):
    await state.update_data(car_vin=message.text)
    await state.set_state(PhotoEstimateForm.phone)
    await message.answer("Введите телефон:")

@router.message(PhotoEstimateForm.phone)
async def process_photo_phone(message: Message, state: FSMContext):
    await state.update_data(phone=message.text.strip().replace("+", ""))
    await state.set_state(PhotoEstimateForm.full_name)
    await message.answer("Укажите ваши ФИО:")

@router.message(PhotoEstimateForm.full_name)
async def process_photo_fullname(message: Message, state: FSMContext):
    await state.update_data(full_name=message.text)
    await state.set_state(PhotoEstimateForm.photos)
    album_data[message.from_user.id] = []
    await message.answer("📷 Отправьте фото повреждений. Когда закончите, напишите любое слово (например, точку `.`).")

@router.message(PhotoEstimateForm.photos, F.photo)
async def collect_photos(message: Message):
    user_id = message.from_user.id
    if user_id not in album_data:
        album_data[user_id] = []
    album_data[user_id].append(message.photo[-1].file_id)
    await message.answer(f"📸 Фото принято ({len(album_data[user_id])}). Отправьте еще или напишите текст для завершения.")

@router.message(PhotoEstimateForm.photos)
async def finish_photo_estimate(message: Message, state: FSMContext, bot: Bot):
    user_id = message.from_user.id
    data = await state.get_data()
    photos = album_data.get(user_id, [])

    admin_header = f"📸 **Оценка по фото**\n📱 `{data['phone']}`\n🚘 *{data['car_brand']} {data['car_model']}*\n👤 *{data['full_name']}*"
    try:
        if photos:
            media_builder = MediaGroupBuilder(caption=admin_header)
            for photo_id in photos[:10]:
                media_builder.add(type="photo", media=photo_id)
            await bot.send_media_group(chat_id=ADMIN_CHAT_ID, media=media_builder.build())
        else:
            await bot.send_message(chat_id=ADMIN_CHAT_ID, text=admin_header + "\n(Без фото)", parse_mode="Markdown")
    except Exception:
        pass

    if user_id in album_data:
        del album_data[user_id]

    await message.answer("✅ Фото и заявка переданы в кузовной цех!", reply_markup=main_menu)
    await state.clear()

@router.message(F.text == "📞 Связаться с мастером")
async def btn_contact(message: Message):
    await message.answer("📞 Телефон: `+7 (921) 950-01-10`\nАдрес: СПб, Рубежная ул., 2Л", parse_mode="Markdown")

# --- ВЕБ-СЕРВЕР ДЛЯ MINI APP ---
async def handle_api_user_data(request):
    user_id_str = request.query.get("user_id")
    if not user_id_str:
        return web.json_response({"error": "No user_id"}, status=400)
    
    user_id = int(user_id_str)
    
    # Ищем пользователя в базе по telegram_id
    user_data = None
    user_phone = "Не привязан"
    
    for phone, info in cards_db.items():
        if info.get("user_id") == user_id:
            user_data = info
            user_phone = phone
            break

    if not user_data:
        # Если карты нет, возвращаем дефолтные нули
        return web.json_response({
            "phone": user_phone,
            "turnover": 0,
            "level_name": "Начальный",
            "discount": 0,
            "max_target": 75000,
            "next_text": "Осталось накопить: 75 000 ₽",
            "ref_count": 0,
            "bonus_balance": 0,
            "ref_rate": 1
        })

    turnover = user_data.get("turnover", 0.0)
    level, discount, level_name, max_target = get_discount_level(turnover)
    
    next_target = max_target - turnover if turnover < max_target else 0
    next_text = f"Осталось накопить: {int(next_target)} ₽" if turnover < max_target else "Максимальный уровень достигнут!"

    ref_count = len(user_data.get("referrals_list", []))
    bonus_balance = user_data.get("bonus_balance", 0.0)
    ref_rate = get_referral_cashback_rate(ref_count)

    return web.json_response({
        "phone": user_phone,
        "turnover": int(turnover),
        "level_name": level_name,
        "discount": discount,
        "max_target": max_target,
        "next_text": next_text,
        "ref_count": ref_count,
        "bonus_balance": int(bonus_balance),
        "ref_rate": ref_rate
    })

import asyncio

async def main():
    bot = Bot(token=TOKEN)
    dp = Dispatcher()
    dp.include_router(router)
    
    # 1. Настраиваем веб-сервер aiohttp
    app = web.Application()
    app.router.add_get('/api/user_data', handle_api_user_data)
    app.router.add_static('/', path='./webapp', name='webapp')
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    
    # 2. Сначала запускаем веб-сервер (обязательно для Render)
    await site.start()
    print(f"Веб-сервер запущен на порту {port}")
    
    # 3. Параллельно запускаем опросы бота и держим сервер живым
    await asyncio.gather(
        dp.start_polling(bot)
    )

if __name__ == "__main__":
    asyncio.run(main())
