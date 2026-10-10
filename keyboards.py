from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_menu(is_admin: bool = False) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="📋 Завдання", callback_data="tasks"),
        InlineKeyboardButton(text="👥 Реферали", callback_data="referrals"),
    )
    kb.row(
        InlineKeyboardButton(text="🛒 Магазин", callback_data="shop"),
        InlineKeyboardButton(text="🎟 Промокод", callback_data="promo"),
    )
    kb.row(
        InlineKeyboardButton(text="🎡 Колесо", callback_data="wheel"),
        InlineKeyboardButton(text="💰 Баланс", callback_data="balance"),
    )
    if is_admin:
        kb.row(InlineKeyboardButton(text="👑 Адмін-панель", callback_data="admin_menu"))
    return kb.as_markup()


def back_btn(target: str = "main") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="← Назад", callback_data=target)]]
    )


def tasks_keyboard(tasks: list) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for task in tasks:
        icon = "⭐" if task["reward_type"] == "stars" else "💵"
        kb.row(InlineKeyboardButton(
            text=f"{icon} {task['title']}  (+{task['reward_amt']})",
            callback_data=f"task_{task['id']}",
        ))
    kb.row(InlineKeyboardButton(text="← Назад", callback_data="main"))
    return kb.as_markup()


def task_detail_keyboard(task_id: int, completed: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if not completed:
        kb.row(InlineKeyboardButton(text="✅ Виконати", callback_data=f"do_task_{task_id}"))
    else:
        kb.row(InlineKeyboardButton(text="✔ Вже виконано", callback_data="noop"))
    kb.row(InlineKeyboardButton(text="← Назад", callback_data="tasks"))
    return kb.as_markup()


def balance_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="⭐ Вивести Stars", callback_data="payout_stars"),
        InlineKeyboardButton(text="💵 Вивести USDT", callback_data="payout_usdt"),
    )
    kb.row(InlineKeyboardButton(text="← Назад", callback_data="main"))
    return kb.as_markup()


def shop_keyboard(lots: list) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for lot in lots:
        kb.row(InlineKeyboardButton(
            text=f"👥 {lot['ref_count']} рефералів — {lot['price_usdt']} USDT",
            callback_data=f"buy_lot_{lot['id']}",
        ))
    kb.row(InlineKeyboardButton(text="← Назад", callback_data="main"))
    return kb.as_markup()


def wheel_keyboard(spins: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if spins > 0:
        kb.row(InlineKeyboardButton(
            text=f"🎡 Крутити ({spins} спін{'ів' if spins > 1 else ''})",
            callback_data="wheel_spin",
        ))
    kb.row(InlineKeyboardButton(text="← Назад", callback_data="main"))
    return kb.as_markup()


def wheel_again_keyboard(spins: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if spins > 0:
        kb.row(InlineKeyboardButton(
            text=f"🎡 Ще раз! ({spins} залишилось)",
            callback_data="wheel_spin",
        ))
    kb.row(InlineKeyboardButton(text="← Назад", callback_data="main"))
    return kb.as_markup()


def referrals_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="🎡 Колесо фортуни", callback_data="wheel"))
    kb.row(InlineKeyboardButton(text="← Назад", callback_data="main"))
    return kb.as_markup()


# ── Admin keyboards ───────────────────────────────────────────────────────────

def admin_menu_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="➕ Додати завдання", callback_data="adm_add_task"),
        InlineKeyboardButton(text="📋 Завдання", callback_data="adm_list_tasks"),
    )
    kb.row(
        InlineKeyboardButton(text="🎟 Новий промокод", callback_data="adm_add_promo"),
        InlineKeyboardButton(text="🛒 Додати лот", callback_data="adm_add_lot"),
    )
    kb.row(
        InlineKeyboardButton(text="💸 Нарахувати бонус", callback_data="adm_give_bonus"),
        InlineKeyboardButton(text="📩 Заявки на виплату", callback_data="adm_payouts"),
    )
    kb.row(InlineKeyboardButton(text="← Головна", callback_data="main"))
    return kb.as_markup()


def admin_tasks_keyboard(tasks: list) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for task in tasks:
        kb.row(InlineKeyboardButton(
            text=f"🗑 {task['title']}",
            callback_data=f"adm_del_task_{task['id']}",
        ))
    kb.row(InlineKeyboardButton(text="← Адмін", callback_data="admin_menu"))
    return kb.as_markup()


def admin_payout_keyboard(payout_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="✅ Підтвердити", callback_data=f"adm_pay_ok_{payout_id}"),
        InlineKeyboardButton(text="❌ Відхилити", callback_data=f"adm_pay_no_{payout_id}"),
    )
    kb.row(InlineKeyboardButton(text="← Адмін", callback_data="admin_menu"))
    return kb.as_markup()


def cancel_fsm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="✖ Скасувати", callback_data="adm_cancel_fsm")]]
    )
