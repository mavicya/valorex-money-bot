import aiosqlite
import os
import random

DB_PATH = os.getenv("DB_PATH", "valorex.db")

# Колесо фортуни — сектори (prize_type, amount, weight)
WHEEL_SECTORS = [
    ("stars", 100,  35),
    ("stars", 250,  25),
    ("usdt",  1.0,  20),
    ("usdt",  3.0,  12),
    ("stars", 500,   6),
    ("usdt",  10.0,  2),
]

# Тригери спінів: при досягненні N рефералів видається спін
SPIN_TRIGGERS = {3, 5, 10}

WELCOME_STARS = 50  # зірки при першому /start


def spin_wheel() -> tuple[str, float]:
    """Повертає (prize_type, amount) зі зваженою рандомізацією."""
    population = [(t, a) for t, a, w in WHEEL_SECTORS for _ in range(w)]
    return random.choice(population)


async def get_db() -> aiosqlite.Connection:
    conn = await aiosqlite.connect(DB_PATH)
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA journal_mode=WAL")
    return conn


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA journal_mode=WAL")

        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id              INTEGER PRIMARY KEY,
                username        TEXT,
                full_name       TEXT,
                stars           REAL    NOT NULL DEFAULT 0,
                usdt            REAL    NOT NULL DEFAULT 0,
                referrer_id     INTEGER,
                spins_available INTEGER NOT NULL DEFAULT 0,
                spins_used      TEXT    NOT NULL DEFAULT '',
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Migration: add new columns if upgrading existing DB
        for col, definition in [
            ("spins_available", "INTEGER NOT NULL DEFAULT 0"),
            ("spins_used",      "TEXT    NOT NULL DEFAULT ''"),
        ]:
            try:
                await db.execute(f"ALTER TABLE users ADD COLUMN {col} {definition}")
            except Exception:
                pass

        await db.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT    NOT NULL,
                description TEXT    NOT NULL,
                reward_type TEXT    NOT NULL CHECK(reward_type IN ('stars', 'usdt')),
                reward_amt  REAL    NOT NULL,
                is_active   INTEGER NOT NULL DEFAULT 1,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS task_completions (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL,
                task_id    INTEGER NOT NULL,
                completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, task_id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS promocodes (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                code        TEXT    NOT NULL UNIQUE,
                bonus_type  TEXT    NOT NULL CHECK(bonus_type IN ('stars', 'usdt')),
                bonus_amt   REAL    NOT NULL,
                max_uses    INTEGER NOT NULL DEFAULT 1,
                used_count  INTEGER NOT NULL DEFAULT 0,
                is_active   INTEGER NOT NULL DEFAULT 1,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS promo_activations (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL,
                promo_id   INTEGER NOT NULL,
                activated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, promo_id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS referral_lots (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                ref_count   INTEGER NOT NULL,
                price_usdt  REAL    NOT NULL,
                is_active   INTEGER NOT NULL DEFAULT 1,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS payout_requests (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                method      TEXT    NOT NULL CHECK(method IN ('stars', 'usdt')),
                amount      REAL    NOT NULL,
                wallet      TEXT,
                status      TEXT    NOT NULL DEFAULT 'pending'
                                CHECK(status IN ('pending', 'approved', 'rejected')),
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS spin_history (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id      INTEGER NOT NULL,
                prize_type   TEXT    NOT NULL,
                prize_amount REAL    NOT NULL,
                spun_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.commit()


# ── User helpers ──────────────────────────────────────────────────────────────

async def get_or_create_user(
    user_id: int,
    username: str | None,
    full_name: str,
    referrer_id: int | None = None,
) -> tuple[aiosqlite.Row, bool]:
    """Returns (user_row, is_new)."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        row = await (await db.execute("SELECT * FROM users WHERE id = ?", (user_id,))).fetchone()
        if row:
            return row, False

        # New user — grant welcome stars
        await db.execute(
            "INSERT INTO users (id, username, full_name, referrer_id, stars) VALUES (?, ?, ?, ?, ?)",
            (user_id, username, full_name, referrer_id, WELCOME_STARS),
        )

        # Referral logic
        if referrer_id:
            ref_row = await (await db.execute(
                "SELECT * FROM users WHERE id = ?", (referrer_id,)
            )).fetchone()
            if ref_row:
                new_ref_count = await _count_referrals_tx(db, referrer_id) + 1
                # Grant spin if milestone hit
                spin_grant = 0
                used_str: str = ref_row["spins_used"] if ref_row["spins_used"] else ""
                used_set = set(int(x) for x in used_str.split(",") if x.isdigit())
                for trigger in SPIN_TRIGGERS:
                    if new_ref_count >= trigger and trigger not in used_set:
                        spin_grant += 1
                        used_set.add(trigger)
                new_used_str = ",".join(str(x) for x in sorted(used_set))
                await db.execute(
                    """UPDATE users
                       SET spins_available = spins_available + ?,
                           spins_used = ?
                       WHERE id = ?""",
                    (spin_grant, new_used_str, referrer_id),
                )

        await db.commit()
        new_row = await (await db.execute("SELECT * FROM users WHERE id = ?", (user_id,))).fetchone()
        return new_row, True


async def _count_referrals_tx(db: aiosqlite.Connection, user_id: int) -> int:
    row = await (await db.execute(
        "SELECT COUNT(*) FROM users WHERE referrer_id = ?", (user_id,)
    )).fetchone()
    return row[0] if row else 0


async def get_user(user_id: int) -> aiosqlite.Row | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        return await (await db.execute("SELECT * FROM users WHERE id = ?", (user_id,))).fetchone()


async def get_referral_count(user_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        row = await (await db.execute(
            "SELECT COUNT(*) FROM users WHERE referrer_id = ?", (user_id,)
        )).fetchone()
        return row[0] if row else 0


async def adjust_balance(user_id: int, stars: float = 0, usdt: float = 0) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET stars = stars + ?, usdt = usdt + ? WHERE id = ?",
            (stars, usdt, user_id),
        )
        await db.commit()


# ── Wheel of fortune ──────────────────────────────────────────────────────────

async def use_spin(user_id: int) -> tuple[str, float] | None:
    """
    Consumes one spin. Returns (prize_type, amount) or None if no spins left.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        user = await (await db.execute(
            "SELECT spins_available FROM users WHERE id = ?", (user_id,)
        )).fetchone()
        if not user or user["spins_available"] <= 0:
            return None

        prize_type, amount = spin_wheel()

        await db.execute(
            "UPDATE users SET spins_available = spins_available - 1 WHERE id = ?", (user_id,)
        )
        if prize_type == "stars":
            await db.execute(
                "UPDATE users SET stars = stars + ? WHERE id = ?", (amount, user_id)
            )
        else:
            await db.execute(
                "UPDATE users SET usdt = usdt + ? WHERE id = ?", (amount, user_id)
            )
        await db.execute(
            "INSERT INTO spin_history (user_id, prize_type, prize_amount) VALUES (?, ?, ?)",
            (user_id, prize_type, amount),
        )
        await db.commit()
        return prize_type, amount


async def grant_spin(user_id: int, count: int = 1) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET spins_available = spins_available + ? WHERE id = ?",
            (count, user_id),
        )
        await db.commit()


# ── Task helpers ──────────────────────────────────────────────────────────────

async def get_active_tasks() -> list[aiosqlite.Row]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        return await (await db.execute(
            "SELECT * FROM tasks WHERE is_active = 1 ORDER BY created_at DESC"
        )).fetchall()


async def get_task(task_id: int) -> aiosqlite.Row | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        return await (await db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))).fetchone()


async def create_task(title: str, description: str, reward_type: str, reward_amt: float) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO tasks (title, description, reward_type, reward_amt) VALUES (?, ?, ?, ?)",
            (title, description, reward_type, reward_amt),
        )
        await db.commit()
        return cur.lastrowid


async def delete_task(task_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE tasks SET is_active = 0 WHERE id = ?", (task_id,))
        await db.commit()


async def has_completed(user_id: int, task_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        row = await (await db.execute(
            "SELECT 1 FROM task_completions WHERE user_id = ? AND task_id = ?",
            (user_id, task_id),
        )).fetchone()
        return row is not None


async def complete_task(user_id: int, task_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        task = await (await db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))).fetchone()
        if not task:
            return False
        try:
            await db.execute(
                "INSERT INTO task_completions (user_id, task_id) VALUES (?, ?)",
                (user_id, task_id),
            )
            if task["reward_type"] == "stars":
                await db.execute(
                    "UPDATE users SET stars = stars + ? WHERE id = ?",
                    (task["reward_amt"], user_id),
                )
            else:
                await db.execute(
                    "UPDATE users SET usdt = usdt + ? WHERE id = ?",
                    (task["reward_amt"], user_id),
                )
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False


# ── Promo helpers ─────────────────────────────────────────────────────────────

async def get_promo(code: str) -> aiosqlite.Row | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        return await (await db.execute(
            "SELECT * FROM promocodes WHERE code = ? AND is_active = 1", (code,)
        )).fetchone()


async def create_promo(code: str, bonus_type: str, bonus_amt: float, max_uses: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                "INSERT INTO promocodes (code, bonus_type, bonus_amt, max_uses) VALUES (?, ?, ?, ?)",
                (code, bonus_type, bonus_amt, max_uses),
            )
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False


async def activate_promo(user_id: int, promo_id: int, bonus_type: str, bonus_amt: float) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                "INSERT INTO promo_activations (user_id, promo_id) VALUES (?, ?)",
                (user_id, promo_id),
            )
            await db.execute(
                "UPDATE promocodes SET used_count = used_count + 1 WHERE id = ?", (promo_id,)
            )
            await db.execute(
                "UPDATE promocodes SET is_active = 0 WHERE id = ? AND used_count >= max_uses",
                (promo_id,),
            )
            if bonus_type == "stars":
                await db.execute(
                    "UPDATE users SET stars = stars + ? WHERE id = ?", (bonus_amt, user_id)
                )
            else:
                await db.execute(
                    "UPDATE users SET usdt = usdt + ? WHERE id = ?", (bonus_amt, user_id)
                )
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False


# ── Referral lots ─────────────────────────────────────────────────────────────

async def get_active_lots() -> list[aiosqlite.Row]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        return await (await db.execute(
            "SELECT * FROM referral_lots WHERE is_active = 1 ORDER BY price_usdt ASC"
        )).fetchall()


async def create_lot(ref_count: int, price_usdt: float) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO referral_lots (ref_count, price_usdt) VALUES (?, ?)",
            (ref_count, price_usdt),
        )
        await db.commit()


async def delete_lot(lot_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE referral_lots SET is_active = 0 WHERE id = ?", (lot_id,))
        await db.commit()


# ── Payout ────────────────────────────────────────────────────────────────────

async def create_payout(user_id: int, method: str, amount: float, wallet: str | None) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO payout_requests (user_id, method, amount, wallet) VALUES (?, ?, ?, ?)",
            (user_id, method, amount, wallet),
        )
        await db.commit()
        return cur.lastrowid


async def get_pending_payouts() -> list[aiosqlite.Row]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        return await (await db.execute(
            "SELECT pr.*, u.username, u.full_name FROM payout_requests pr "
            "JOIN users u ON u.id = pr.user_id WHERE pr.status = 'pending' ORDER BY pr.created_at"
        )).fetchall()


async def get_payout(payout_id: int) -> aiosqlite.Row | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        return await (await db.execute(
            "SELECT * FROM payout_requests WHERE id = ?", (payout_id,)
        )).fetchone()


async def update_payout_status(payout_id: int, status: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if status == "rejected":
            row = await (await db.execute(
                "SELECT * FROM payout_requests WHERE id = ?", (payout_id,)
            )).fetchone()
            if row:
                if row["method"] == "stars":
                    await db.execute(
                        "UPDATE users SET stars = stars + ? WHERE id = ?",
                        (row["amount"], row["user_id"]),
                    )
                else:
                    await db.execute(
                        "UPDATE users SET usdt = usdt + ? WHERE id = ?",
                        (row["amount"], row["user_id"]),
                    )
        await db.execute(
            "UPDATE payout_requests SET status = ? WHERE id = ?", (status, payout_id)
        )
        await db.commit()
