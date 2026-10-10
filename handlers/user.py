import asyncio
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import database as db
from database import WELCOME_STARS, SPIN_TRIGGERS, WHEEL_SECTORS
from keyboards import (
    main_menu, back_btn, tasks_keyboard, task_detail_keyboard,
    balance_keyboard, shop_keyboard, wheel_keyboard, wheel_again_keyboard,
    referrals_keyboard,
)
from config import ADMIN_IDS

router = Router()


class PromoState(StatesGroup):
    waiting_code = State()


class PayoutState(StatesGroup):
    waiting_amount = State()
    waiting_wallet = State()


# ── Wheel display helper ───────────────────────────────────────────────────────

WHEEL_DISPLAY = [
    ("⭐", "100 Stars",  "35%"),
    ("⭐", "250 Stars",  "25%"),
    ("💵", "1 USDT",    "20%"),
    ("💵", "3 USDT",    "12%"),
    ("⭐", "500 Stars",  " 6%"),
    ("💎", "10 USDT",   " 2%"),
]

def wheel_sectors_text() -> str:
    lines = []
    for icon, prize, chance in WHEEL_DISPLAY:
        lines.append(f"{icon} {prize:<12} {chance}")
    return "\n".join(lines)


# ── /start ────────────────────────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message):
    args = message.text.split()
    referrer_id = None
    if len(args) > 1 and args[1].startswith("ref_"):
        try:
            ref = int(args[1][4:])
            if ref != message.from_user.id:
                referrer_id = ref
        except ValueError:
            pass

    user, is_new = await db.get_or_create_user(
        user_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
        referrer_id=referrer_id,
    )

    is_admin = message.from_user.id in ADMIN_IDS

    if is_new:
        # Welcome screen — hook
        await message.answer(
            f"⚡️ <b>ValoreX Money</b>\n\n"
            f"Вітаємо! Тобі одразу нараховано\n\n"
            f"<b>⭐ {WELCOME_STARS} Telegram Stars</b>\n\n"
            f"Виконуй завдання, запрошуй друзів та крути колесо фортуни — "
            f"виводь реальні Stars та USDT.\n\n"
            f"📌 За кожні 3 / 5 / 10 запрошених — безкоштовний спін!",
            parse_mode="HTML",
        )
        await asyncio.sleep(0.4)
        await message.answer(
            "👇 Головне меню:",
            reply_markup=main_menu(is_admin),
        )
    else:
        await message.answer(
            "🏠 <b>Головне меню</b>\n\nОбирай розділ 👇",
            reply_markup=main_menu(is_admin),
            parse_mode="HTML",
        )


# ── Main menu ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "main")
async def cb_main(call: CallbackQuery, state: FSMContext):
    await state.clear()
    is_admin = call.from_user.id in ADMIN_IDS
    await call.message.edit_text(
        "🏠 <b>Головне меню</b>\n\nОбирай розділ 👇",
        reply_markup=main_menu(is_admin),
        parse_mode="HTML",
    )


# ── Tasks ─────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "tasks")
async def cb_tasks(call: CallbackQuery):
    tasks = await db.get_active_tasks()
    if not tasks:
        await call.message.edit_text(
            "📋 <b>Завдання</b>\n\nПоки немає активних завдань. Зайди пізніше!",
            reply_markup=back_btn("main"),
            parse_mode="HTML",
        )
        return
    await call.message.edit_text(
        "📋 <b>Активні завдання</b>\n\nОбери завдання зі списку:",
        reply_markup=tasks_keyboard(tasks),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("task_"))
async def cb_task_detail(call: CallbackQuery):
    try:
        task_id = int(call.data.split("_")[1])
    except (IndexError, ValueError):
        await call.answer("Помилка")
        return
    task = await db.get_task(task_id)
    if not task:
        await call.answer("Завдання не знайдено")
        return
    completed = await db.has_completed(call.from_user.id, task_id)
    icon = "⭐" if task["reward_type"] == "stars" else "💵"
    status = "✅ Виконано" if completed else "⏳ Не виконано"
    await call.message.edit_text(
        f"<b>{task['title']}</b>\n\n"
        f"{task['description']}\n\n"
        f"{icon} Нагорода: <b>{task['reward_amt']} {task['reward_type'].upper()}</b>\n"
        f"Статус: {status}",
        reply_markup=task_detail_keyboard(task_id, completed),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("do_task_"))
async def cb_do_task(call: CallbackQuery):
    try:
        task_id = int(call.data.split("_")[2])
    except (IndexError, ValueError):
        await call.answer("Помилка")
        return
    ok = await db.complete_task(call.from_user.id, task_id)
    if ok:
        task = await db.get_task(task_id)
        icon = "⭐" if task["reward_type"] == "stars" else "💵"
        await call.answer(f"🎉 Нараховано {task['reward_amt']} {icon}", show_alert=True)
        await cb_tasks(call)
    else:
        await call.answer("Ти вже виконав це завдання!", show_alert=True)


@router.callback_query(F.data == "noop")
async def cb_noop(call: CallbackQuery):
    await call.answer()


# ── Referrals ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "referrals")
async def cb_referrals(call: CallbackQuery):
    uid = call.from_user.id
    count = await db.get_referral_count(uid)
    user = await db.get_user(uid)
    spins = user["spins_available"] if user else 0
    link = f"https://t.me/ValoreXmoney_bot?start=ref_{uid}"

    # Progress to next spin trigger
    next_trigger = next((t for t in sorted(SPIN_TRIGGERS) if t > count), None)
    progress_line = ""
    if next_trigger:
        left = next_trigger - count
        progress_line = f"\n⏳ До наступного спіну: ще <b>{left}</b> друзів"

    spin_line = f"\n🎡 Доступних спінів: <b>{spins}</b>" if spins > 0 else ""

    milestones = "  ".join(
        f"{'✅' if count >= t else '⭕'} {t} рефів" for t in sorted(SPIN_TRIGGERS)
    )

    await call.message.edit_text(
        f"👥 <b>Реферальна система</b>\n\n"
        f"За кожні <b>3 → 5 → 10</b> запрошених друзів\n"
        f"ти отримуєш безкоштовний 🎡 <b>спін колеса</b>!\n\n"
        f"Призи: до <b>10 USDT</b> або <b>500 Stars</b> за один спін.\n\n"
        f"🔗 Твоє посилання:\n<code>{link}</code>\n\n"
        f"👤 Запрошено: <b>{count}</b>\n"
        f"{milestones}"
        f"{progress_line}"
        f"{spin_line}",
        reply_markup=referrals_keyboard(),
        parse_mode="HTML",
    )


# ── Wheel of fortune ──────────────────────────────────────────────────────────

@router.callback_query(F.data == "wheel")
async def cb_wheel(call: CallbackQuery):
    user = await db.get_user(call.from_user.id)
    spins = user["spins_available"] if user else 0

    sectors_text = wheel_sectors_text()
    if spins > 0:
        intro = f"🎡 <b>Колесо фортуни</b>\n\nУ тебе <b>{spins}</b> спін{'ів' if spins != 1 else ''}!\n\n"
    else:
        intro = (
            "🎡 <b>Колесо фортуни</b>\n\n"
            "Спінів немає 😔\n"
            "Запроси <b>3 друзів</b> — отримаєш безкоштовний спін!\n\n"
        )

    await call.message.edit_text(
        f"{intro}"
        f"<b>Сектори:</b>\n"
        f"<code>{sectors_text}</code>",
        reply_markup=wheel_keyboard(spins),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "wheel_spin")
async def cb_wheel_spin(call: CallbackQuery):
    # Анімація — редагуємо повідомлення
    frames = ["🎡", "🌀", "💫", "🎯"]
    await call.answer()

    msg = await call.message.edit_text("🎡 Крутимо колесо...", parse_mode="HTML")

    for frame in frames:
        await asyncio.sleep(0.4)
        try:
            await msg.edit_text(f"{frame} Крутимо...", parse_mode="HTML")
        except Exception:
            pass

    result = await db.use_spin(call.from_user.id)

    if result is None:
        await msg.edit_text(
            "❌ Спінів немає. Запроси друзів, щоб отримати спін!",
            reply_markup=back_btn("referrals"),
        )
        return

    prize_type, amount = result
    user = await db.get_user(call.from_user.id)
    spins_left = user["spins_available"] if user else 0

    if prize_type == "stars":
        icon = "⭐"
        prize_str = f"{int(amount)} Stars"
    else:
        icon = "💎"
        prize_str = f"{amount:.1f} USDT"

    await asyncio.sleep(0.3)
    await msg.edit_text(
        f"🎉 <b>Результат!</b>\n\n"
        f"{icon} Ти виграв: <b>{prize_str}</b>\n\n"
        f"Нараховано на баланс автоматично.",
        reply_markup=wheel_again_keyboard(spins_left),
        parse_mode="HTML",
    )


# ── Shop ──────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "shop")
async def cb_shop(call: CallbackQuery):
    lots = await db.get_active_lots()
    if not lots:
        await call.message.edit_text(
            "🛒 <b>Магазин рефералів</b>\n\nПоки немає доступних лотів.",
            reply_markup=back_btn("main"),
            parse_mode="HTML",
        )
        return
    await call.message.edit_text(
        "🛒 <b>Магазин рефералів</b>\n\n"
        "Купуй рефералів за накопичені USDT.\n"
        "Оберіть лот:",
        reply_markup=shop_keyboard(lots),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("buy_lot_"))
async def cb_buy_lot(call: CallbackQuery):
    try:
        lot_id = int(call.data.split("_")[2])
    except (IndexError, ValueError):
        await call.answer("Помилка")
        return
    lots = await db.get_active_lots()
    lot = next((l for l in lots if l["id"] == lot_id), None)
    if not lot:
        await call.answer("Лот більше недоступний", show_alert=True)
        return
    user = await db.get_user(call.from_user.id)
    if not user or user["usdt"] < lot["price_usdt"]:
        await call.answer("❌ Недостатньо USDT на балансі", show_alert=True)
        return
    await db.adjust_balance(call.from_user.id, usdt=-lot["price_usdt"])
    await call.answer(
        f"✅ Придбано {lot['ref_count']} рефералів за {lot['price_usdt']} USDT!\n"
        "Реферали будуть зараховані адміністратором.",
        show_alert=True,
    )
    await cb_shop(call)


# ── Promo ─────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "promo")
async def cb_promo(call: CallbackQuery, state: FSMContext):
    await state.set_state(PromoState.waiting_code)
    await call.message.edit_text(
        "🎟 <b>Промокод</b>\n\nВведи свій промокод:",
        reply_markup=back_btn("main"),
        parse_mode="HTML",
    )


@router.message(PromoState.waiting_code)
async def process_promo(message: Message, state: FSMContext):
    await state.clear()
    code = message.text.strip().upper()
    promo = await db.get_promo(code)
    if not promo:
        await message.answer(
            "❌ Промокод не знайдено або вже вичерпаний.",
            reply_markup=back_btn("main"),
        )
        return
    ok = await db.activate_promo(
        message.from_user.id, promo["id"], promo["bonus_type"], promo["bonus_amt"]
    )
    if ok:
        icon = "⭐" if promo["bonus_type"] == "stars" else "💵"
        await message.answer(
            f"✅ Промокод активовано!\n"
            f"Нараховано: <b>{promo['bonus_amt']} {promo['bonus_type'].upper()}</b> {icon}",
            reply_markup=back_btn("main"),
            parse_mode="HTML",
        )
    else:
        await message.answer(
            "❌ Ти вже використовував цей промокод.",
            reply_markup=back_btn("main"),
        )


# ── Balance & payout ──────────────────────────────────────────────────────────

@router.callback_query(F.data == "balance")
async def cb_balance(call: CallbackQuery):
    user = await db.get_user(call.from_user.id)
    stars = user["stars"] if user else 0
    usdt = user["usdt"] if user else 0
    spins = user["spins_available"] if user else 0
    await call.message.edit_text(
        f"💰 <b>Мій баланс</b>\n\n"
        f"⭐ Telegram Stars: <b>{int(stars)}</b>\n"
        f"💵 USDT: <b>{usdt:.2f}</b>\n"
        f"🎡 Спінів: <b>{spins}</b>",
        reply_markup=balance_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(F.data.in_({"payout_stars", "payout_usdt"}))
async def cb_payout_start(call: CallbackQuery, state: FSMContext):
    method = "stars" if call.data == "payout_stars" else "usdt"
    user = await db.get_user(call.from_user.id)
    available = user["stars"] if method == "stars" else user["usdt"]
    if available <= 0:
        await call.answer("❌ Недостатньо коштів для виплати", show_alert=True)
        return
    await state.update_data(method=method, available=available)
    await state.set_state(PayoutState.waiting_amount)
    icon = "⭐" if method == "stars" else "💵"
    await call.message.edit_text(
        f"💸 <b>Виплата {method.upper()}</b>\n\n"
        f"Доступно: <b>{available:.2f} {icon}</b>\n\n"
        f"Введи суму для виведення:",
        reply_markup=back_btn("balance"),
        parse_mode="HTML",
    )


@router.message(PayoutState.waiting_amount)
async def payout_amount(message: Message, state: FSMContext):
    try:
        amount = float(message.text.strip().replace(",", "."))
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введи коректну суму (число більше 0):")
        return
    data = await state.get_data()
    if amount > data["available"]:
        await message.answer(
            f"❌ Перевищує баланс ({data['available']:.2f}). Введи меншу суму:"
        )
        return
    await state.update_data(amount=amount)
    method = data["method"]
    if method == "usdt":
        await state.set_state(PayoutState.waiting_wallet)
        await message.answer("💳 Введи адресу USDT-гаманця (TRC-20):")
    else:
        await state.clear()
        payout_id = await db.create_payout(message.from_user.id, method, amount, None)
        await db.adjust_balance(message.from_user.id, stars=-amount)
        await message.answer(
            f"✅ Заявку #{payout_id} на виплату <b>{int(amount)} Stars</b> надіслано!\n"
            "Адміністратор обробить її найближчим часом.",
            reply_markup=back_btn("main"),
            parse_mode="HTML",
        )


@router.message(PayoutState.waiting_wallet)
async def payout_wallet(message: Message, state: FSMContext):
    wallet = message.text.strip()
    if len(wallet) < 20:
        await message.answer("❌ Схоже, адреса некоректна. Спробуй ще раз:")
        return
    data = await state.get_data()
    await state.clear()
    payout_id = await db.create_payout(
        message.from_user.id, data["method"], data["amount"], wallet
    )
    await db.adjust_balance(message.from_user.id, usdt=-data["amount"])
    await message.answer(
        f"✅ Заявку #{payout_id} на виплату <b>{data['amount']:.2f} USDT</b> надіслано!\n"
        f"Гаманець: <code>{wallet}</code>\n"
        "Адміністратор обробить її найближчим часом.",
        reply_markup=back_btn("main"),
        parse_mode="HTML",
    )
