import os
import json
import asyncio
from aiohttp import web
from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import Command
from aiogram.types import Message, WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton

TOKEN = "7949432655:AAHx-1u7W07rK9bI09V7NlG0WlW_UvE529I"
WEBAPP_URL = "https://botakmakm.onrender.com/index.html"
ADMIN_IDS = [8633592767]

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
        return 5, 1000000, "Осталось до 7%: " + f"{1000000 - turnover:,} ₽"
    elif turnover >= 300000:
        return 4, 500000, "Осталось до 5%: " + f"{500000 - turnover:,} ₽"
    elif turnover >= 200000:
        return 3, 300000, "Осталось до 4%: " + f"{300000 - turnover:,} ₽"
    elif turnover >= 100000:
        return 2, 200000, "Осталось до 3%: " + f"{200000 - turnover:,} ₽"
    else:
        return 1, 100000, "Осталось до 2%: " + f"{100000 - turnover:,} ₽"

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

# Персональная скидка (отдельный блок)
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

bot = Bot(token=TOKEN)
dp = Dispatcher()
router = Router()

def get_main_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Карта лояльности и Авто", web_app=WebAppInfo(url=WEBAPP_URL))],
        [InlineKeyboardButton(text="🎁 Реферальная программа", callback_data="ref_menu")],
        [InlineKeyboardButton(text="📞 Связаться с мастером", callback_data="contact")]
    ])

@router.message(Command("start"))
async def cmd_start(message: Message):
    user_id = str(message.from_user.id)
    args = message.text.split()
    
    db = load_db()
    if user_id not in db:
        db[user_id] = {
            "phone": "Не указан",
            "turnover": 0.0,
            "bonus_balance": 0.0,
            "active_refs": 0,
            "invited_by": None,
            "first_visit_done": False,
            "car": {"brand": "", "model": "", "vin": "", "plate": ""}
        }
        if len(args) > 1:
            referrer_id = args[1]
            if referrer_id != user_id and referrer_id in db:
                db[user_id]["invited_by"] = referrer_id
                db[user_id]["bonus_balance"] += 750.0 # Приветственный бонус другу
        save_db(db)

    await message.answer(
        "👋 Добро пожаловать в **АКМ Авто**!\n\n"
        "Ваша карта лояльности, кэшбэк и 750 ₽ на первый визит активированы. Откройте приложение, чтобы заполнить данные авто и следить за бонусами.",
        reply_markup=get_main_keyboard(),
        parse_mode="Markdown"
    )

@router.callback_query(F.data == "ref_menu")
async def ref_menu_callback(callback: Message):
    user_id = str(callback.from_user.id)
    db = load_db()
    user = db.get(user_id, {"active_refs": 0, "bonus_balance": 0})
    ref_rate = get_referral_passive_rate(user.get("active_refs", 0))
    ref_link = f"https://t.me/akmautospb_bot?start={user_id}"
    
    text = (
        "🎁 **Реферальная программа АКМ Авто**\n\n"
        "1️⃣ Друг получает **750 ₽** на первый визит.\n"
        "2️⃣ Вы получаете **10%** от чека его первого визита (до 5 000 бонусов).\n"
        "3️⃣ Вы получаете **постоянный пассивный кэшбэк** со всех последующих визитов ваших друзей!\n\n"
        f"👥 Приглашено друзей (с визитами): **{user.get('active_refs', 0)} чел.**\n"
        f"📈 Ваш текущий реферальный процент с друзей: **{ref_rate}%**\n\n"
        f"🔗 Ваша реферальная ссылка:\n`{ref_link}`"
    )
    await callback.message.answer(text, parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "contact")
async def contact_callback(callback: Message):
    await callback.message.answer("📞 Телефон: +7 (999) 000-00-00\n📍 Адрес: ул. Автомобильная, 1")
    await callback.answer()

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
        db[client_id] = {"phone": "Касса", "turnover": 0.0, "bonus_balance": 0.0, "active_refs": 0, "invited_by": None, "first_visit_done": False, "car": {}}
    
    client = db[client_id]
    
    # 1. Если это первый визит — обрабатываем бонус пригласившему
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
                    f"🎉 Ваш друг совершил первый визит на сумму {amount:,.0f} ₽!\n"
                    f"🎁 Вам начислено 10% за первый визит: *{ref_bonus:,.0f} бонусов*.", 
                    parse_mode="Markdown"
                )
            except:
                pass

    # 2. Увеличиваем личный оборот клиента и начисляем ЕМУ его личный кэшбэк
    client["turnover"] += amount
    personal_rate, _, _ = get_personal_cashback_rate(client["turnover"])
    client_cashback = amount * (personal_rate / 100.0)
    client["bonus_balance"] += client_cashback

    # 3. Начисляем РЕФЕРАЛЬНЫЙ кэшбэк тому, кто пригласил этого клиента (если есть пригласивший)
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
                    f"💰 Ваш реферал совершил визит на {amount:,.0f} ₽!\n"
                    f"📈 Вам начислен пассивный кэшбэк ({passive_rate}%): *{passive_bonus:,.0f} бонусов*.",
                    parse_mode="Markdown"
                )
            except:
                pass

    save_db(db)
    await message.answer(
        f"✅ Визит успешно зарегистрирован!\n"
        f"👤 Клиент: {client_id} | Чек: {amount:,.0f} ₽\n"
        f"💵 Личный кэшбэк клиенту ({personal_rate}%): {client_cashback:,.0f} бонусов"
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
        return await message.answer("❌ Недостаточно бонусов.")
    db[client_id]["bonus_balance"] -= burn_amount
    save_db(db)
    await message.answer(f"✅ Успешно списано {burn_amount} бонусов у {client_id}.")

# === API ДЛЯ MINI APP ===
async def handle_api_user_data(request):
    user_id = request.rel_url.query.get('user_id')
    db = load_db()
    
    if not user_id or user_id not in db:
        return web.json_response({
            "phone": "Не указан",
            "turnover": 0,
            "discount": 0,
            "personal_cashback": 1,
            "referral_passive_rate": 0,
            "ref_count": 0,
            "bonus_balance": 750,
            "next_text": "Осталось до личного кэшбэка 2%: 100 000 ₽",
            "car": {"brand": "", "model": "", "vin": "", "plate": ""}
        })
    
    user = db[user_id]
    discount = calculate_discount(user["turnover"])
    personal_cashback, _, next_text = get_personal_cashback_rate(user["turnover"])
    referral_passive_rate = get_referral_passive_rate(user.get("active_refs", 0))
    
    response_data = {
        "phone": user.get("phone", "Не указан"),
        "turnover": user["turnover"],
        "discount": discount,
        "personal_cashback": personal_cashback,
        "referral_passive_rate": referral_passive_rate,
        "ref_count": user.get("active_refs", 0),
        "bonus_balance": user["bonus_balance"],
        "next_text": next_text,
        "car": user.get("car", {"brand": "", "model": "", "vin": "", "plate": ""})
    }
    return web.json_response(response_data)

async def handle_save_car(request):
    user_id = request.rel_url.query.get('user_id')
    data = await request.json()
    db = load_db()
    if user_id in db:
        db[user_id]["car"] = data
        save_db(db)
        return web.json_response({"success": True})
    return web.json_response({"success": False})

async def main():
    dp.include_router(router)
    app = web.Application()
    app.router.add_get('/api/user_data', handle_api_user_data)
    app.router.add_post('/api/save_car', handle_save_car)
    app.router.add_static('/', path='./webapp', name='webapp')
    
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"Сервер запущен на порту {port}")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
