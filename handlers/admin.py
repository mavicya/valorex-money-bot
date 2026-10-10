from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.filters import BaseFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import database as db
from config import ADMIN_IDS
from keyboards import (
    admin_menu_keyboard, admin_tasks_keyboard,
    admin_payout_keyboard, cancel_fsm_keyboard, back_btn, main_menu,
)

router = Router()


# ── Admin filter ──────────────────────────────────────────────────────────────

class IsAdmin(BaseFilter):
    async def __call__(self, event: Message | CallbackQuery) -> bool:
        uid = event.from_user.id if hasattr(event, "from_user") else 0
        return uid in ADMIN_IDS


router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


# ── FSM States ────────────────────────────────────────────────────────────────

class AddTaskFSM(StatesGroup):
    title = State()
    description = State()
    reward_type = State()
    reward_amt = State()


class AddPromoFSM(StatesGroup):
    code = State()
    bonus_type = State()
    bonus_amt = State()
    max_uses = State()


class AddLotFSM(StatesGroup):
    ref_count = State()
    price_usdt = State()


class GiveBonusFSM(StatesGroup):
    user_id = State()
    bonus_type = State()
    amount = State()


# ── Admin menu ────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin_menu")
async def cb_admin_menu(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text(
        "👑 <b>Адмін-панель</b>\n\nОбери дію:",
        reply_markup=admin_menu_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "adm_cancel_fsm")
async def cb_cancel_fsm(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text(
        "👑 <b>Адмін-панель</b>\n\nОбери дію:",
        reply_markup=admin_menu_keyboard(),
        parse_mode="HTML",
    )


# ── Tasks management ──────────────────────────────────────────────────────────

@router.callback_query(F.data == "adm_list_tasks")
async def cb_adm_tasks(call: CallbackQuery):
    tasks = await db.get_active_tasks()
    if not tasks:
        await call.message.edit_text(
            "📋 Активних завдань немає.",
            reply_markup=back_btn("admin_menu"),
        )
        return
    await call.message.edit_text(
        "📋 <b>Активні завдання</b>\n\nНатисни, щоб видалити:",
        reply_markup=admin_tasks_keyboard(tasks),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("adm_del_task_"))
async def cb_del_task(call: CallbackQuery):
    try:
        task_id = int(call.data.split("_")[3])
    except (IndexError, ValueError):
        await call.answer("Помилка")
        return
    await db.delete_task(task_id)
    await call.answer("🗑 Завдання видалено", show_alert=True)
    await cb_adm_tasks(call)


# Add Task FSM ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "adm_add_task")
async def adm_add_task_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(AddTaskFSM.title)
    await call.message.edit_text(
        "➕ <b>Нове завдання</b>\n\nВведи <b>назву</b> завдання:",
        reply_markup=cancel_fsm_keyboard(),
        parse_mode="HTML",
    )


@router.message(AddTaskFSM.title)
async def adm_task_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text.strip())
    await state.set_state(AddTaskFSM.description)
    await message.answer("📝 Введи <b>опис</b> завдання:", parse_mode="HTML",
                         reply_markup=cancel_fsm_keyboard())


@router.message(AddTaskFSM.description)
async def adm_task_desc(message: Message, state: FSMContext):
    await state.update_data(description=message.text.strip())
    await state.set_state(AddTaskFSM.reward_type)
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⭐ Stars", callback_data="rtype_stars"),
            InlineKeyboardButton(text="💵 USDT", callback_data="rtype_usdt"),
        ],
        [InlineKeyboardButton(text="✖ Скасувати", callback_data="adm_cancel_fsm")],
    ])
    await message.answer("💰 Обери тип нагороди:", reply_markup=kb)


@router.callback_query(F.data.in_({"rtype_stars", "rtype_usdt"}), AddTaskFSM.reward_type)
async def adm_task_rtype(call: CallbackQuery, state: FSMContext):
    rtype = "stars" if call.data == "rtype_stars" else "usdt"
    await state.update_data(reward_type=rtype)
    await state.set_state(AddTaskFSM.reward_amt)
    await call.message.edit_text(
        f"🔢 Введи суму нагороди ({rtype.upper()}):",
        reply_markup=cancel_fsm_keyboard(),
    )


@router.message(AddTaskFSM.reward_amt)
async def adm_task_amt(message: Message, state: FSMContext):
    try:
        amt = float(message.text.strip().replace(",", "."))
        if amt <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введи коректне число більше 0:")
        return
    data = await state.get_data()
    await state.clear()
    task_id = await db.create_task(data["title"], data["description"], data["reward_type"], amt)
    await message.answer(
        f"✅ Завдання <b>#{task_id}</b> створено!\n"
        f"<b>{data['title']}</b> → {amt} {data['reward_type'].upper()}",
        reply_markup=back_btn("admin_menu"),
        parse_mode="HTML",
    )


# Add Promo FSM ────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "adm_add_promo")
async def adm_promo_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(AddPromoFSM.code)
    await call.message.edit_text(
        "🎟 <b>Новий промокод</b>\n\nВведи <b>код</b> (напр. BONUS100):",
        reply_markup=cancel_fsm_keyboard(),
        parse_mode="HTML",
    )


@router.message(AddPromoFSM.code)
async def adm_promo_code(message: Message, state: FSMContext):
    code = message.text.strip().upper()
    await state.update_data(code=code)
    await state.set_state(AddPromoFSM.bonus_type)
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⭐ Stars", callback_data="ptype_stars"),
            InlineKeyboardButton(text="💵 USDT", callback_data="ptype_usdt"),
        ],
        [InlineKeyboardButton(text="✖ Скасувати", callback_data="adm_cancel_fsm")],
    ])
    await message.answer("💰 Обери тип бонусу:", reply_markup=kb)


@router.callback_query(F.data.in_({"ptype_stars", "ptype_usdt"}), AddPromoFSM.bonus_type)
async def adm_promo_btype(call: CallbackQuery, state: FSMContext):
    btype = "stars" if call.data == "ptype_stars" else "usdt"
    await state.update_data(bonus_type=btype)
    await state.set_state(AddPromoFSM.bonus_amt)
    await call.message.edit_text(
        f"🔢 Введи суму бонусу ({btype.upper()}):",
        reply_markup=cancel_fsm_keyboard(),
    )


@router.message(AddPromoFSM.bonus_amt)
async def adm_promo_amt(message: Message, state: FSMContext):
    try:
        amt = float(message.text.strip().replace(",", "."))
        if amt <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введи коректне число:")
        return
    await state.update_data(bonus_amt=amt)
    await state.set_state(AddPromoFSM.max_uses)
    await message.answer("🔢 Максимальна кількість активацій:", reply_markup=cancel_fsm_keyboard())


@router.message(AddPromoFSM.max_uses)
async def adm_promo_uses(message: Message, state: FSMContext):
    try:
        uses = int(message.text.strip())
        if uses <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введи ціле число більше 0:")
        return
    data = await state.get_data()
    await state.clear()
    ok = await db.create_promo(data["code"], data["bonus_type"], data["bonus_amt"], uses)
    if ok:
        await message.answer(
            f"✅ Промокод <b>{data['code']}</b> створено!\n"
            f"Бонус: {data['bonus_amt']} {data['bonus_type'].upper()}, ліміт: {uses}",
            reply_markup=back_btn("admin_menu"),
            parse_mode="HTML",
        )
    else:
        await message.answer(
            "❌ Промокод з таким кодом вже існує.",
            reply_markup=back_btn("admin_menu"),
        )


# Add Lot FSM ──────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "adm_add_lot")
async def adm_lot_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(AddLotFSM.ref_count)
    await call.message.edit_text(
        "🛒 <b>Новий лот</b>\n\nВведи кількість рефералів у лоті:",
        reply_markup=cancel_fsm_keyboard(),
        parse_mode="HTML",
    )


@router.message(AddLotFSM.ref_count)
async def adm_lot_count(message: Message, state: FSMContext):
    try:
        count = int(message.text.strip())
        if count <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введи ціле число більше 0:")
        return
    await state.update_data(ref_count=count)
    await state.set_state(AddLotFSM.price_usdt)
    await message.answer("💵 Ціна лоту в USDT:", reply_markup=cancel_fsm_keyboard())


@router.message(AddLotFSM.price_usdt)
async def adm_lot_price(message: Message, state: FSMContext):
    try:
        price = float(message.text.strip().replace(",", "."))
        if price <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введи коректну суму:")
        return
    data = await state.get_data()
    await state.clear()
    await db.create_lot(data["ref_count"], price)
    await message.answer(
        f"✅ Лот додано: {data['ref_count']} рефералів за {price} USDT",
        reply_markup=back_btn("admin_menu"),
    )


# Give Bonus FSM ───────────────────────────────────────────────────────────────

@router.callback_query(F.data == "adm_give_bonus")
async def adm_bonus_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(GiveBonusFSM.user_id)
    await call.message.edit_text(
        "💸 <b>Нарахування бонусу</b>\n\nВведи Telegram ID користувача:",
        reply_markup=cancel_fsm_keyboard(),
        parse_mode="HTML",
    )


@router.message(GiveBonusFSM.user_id)
async def adm_bonus_uid(message: Message, state: FSMContext):
    try:
        uid = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Введи числовий Telegram ID:")
        return
    user = await db.get_user(uid)
    if not user:
        await message.answer("❌ Користувача не знайдено. Перевір ID.")
        return
    await state.update_data(target_uid=uid)
    await state.set_state(GiveBonusFSM.bonus_type)
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⭐ Stars", callback_data="gtype_stars"),
            InlineKeyboardButton(text="💵 USDT", callback_data="gtype_usdt"),
        ],
        [InlineKeyboardButton(text="✖ Скасувати", callback_data="adm_cancel_fsm")],
    ])
    await message.answer(
        f"👤 Користувач: <b>{user['full_name']}</b> (@{user['username']})\n"
        "Обери тип:",
        reply_markup=kb,
        parse_mode="HTML",
    )


@router.callback_query(F.data.in_({"gtype_stars", "gtype_usdt"}), GiveBonusFSM.bonus_type)
async def adm_bonus_type(call: CallbackQuery, state: FSMContext):
    btype = "stars" if call.data == "gtype_stars" else "usdt"
    await state.update_data(bonus_type=btype)
    await state.set_state(GiveBonusFSM.amount)
    await call.message.edit_text(
        f"🔢 Введи суму (негативна — для списання) у {btype.upper()}:",
        reply_markup=cancel_fsm_keyboard(),
    )


@router.message(GiveBonusFSM.amount)
async def adm_bonus_amt(message: Message, state: FSMContext):
    try:
        amount = float(message.text.strip().replace(",", "."))
        if amount == 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введи ненульове число:")
        return
    data = await state.get_data()
    await state.clear()
    if data["bonus_type"] == "stars":
        await db.adjust_balance(data["target_uid"], stars=amount)
    else:
        await db.adjust_balance(data["target_uid"], usdt=amount)
    sign = "+" if amount > 0 else ""
    await message.answer(
        f"✅ Баланс змінено: {sign}{amount} {data['bonus_type'].upper()} "
        f"→ uid <code>{data['target_uid']}</code>",
        reply_markup=back_btn("admin_menu"),
        parse_mode="HTML",
    )


# Payout requests ──────────────────────────────────────────────────────────────

@router.callback_query(F.data == "adm_payouts")
async def cb_adm_payouts(call: CallbackQuery):
    payouts = await db.get_pending_payouts()
    if not payouts:
        await call.message.edit_text(
            "📩 <b>Заявки на виплату</b>\n\nНемає нових заявок.",
            reply_markup=back_btn("admin_menu"),
            parse_mode="HTML",
        )
        return
    for p in payouts:
        name = p["full_name"]
        uname = f"@{p['username']}" if p["username"] else f"id{p['user_id']}"
        wallet = p["wallet"] or "—"
        text = (
            f"📩 <b>Заявка #{p['id']}</b>\n"
            f"👤 {name} ({uname})\n"
            f"💰 {p['amount']} {p['method'].upper()}\n"
            f"💳 Гаманець: <code>{wallet}</code>"
        )
        await call.message.answer(
            text,
            reply_markup=admin_payout_keyboard(p["id"]),
            parse_mode="HTML",
        )
    await call.message.edit_text(
        f"📩 <b>Заявки на виплату</b> — всього: {len(payouts)}\n↓",
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("adm_pay_ok_"))
async def cb_pay_ok(call: CallbackQuery):
    try:
        pid = int(call.data.split("_")[3])
    except (IndexError, ValueError):
        await call.answer("Помилка")
        return
    await db.update_payout_status(pid, "approved")
    await call.answer("✅ Виплату підтверджено", show_alert=True)
    await call.message.edit_reply_markup(reply_markup=None)


@router.callback_query(F.data.startswith("adm_pay_no_"))
async def cb_pay_no(call: CallbackQuery):
    try:
        pid = int(call.data.split("_")[3])
    except (IndexError, ValueError):
        await call.answer("Помилка")
        return
    await db.update_payout_status(pid, "rejected")
    await call.answer("❌ Виплату відхилено, баланс повернено", show_alert=True)
    await call.message.edit_reply_markup(reply_markup=None)
