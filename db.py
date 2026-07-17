import sqlite3
import datetime

DB_PATH = "bot.db"


def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        telegram_id INTEGER PRIMARY KEY,
        username TEXT,
        language TEXT,
        is_vip INTEGER DEFAULT 0,
        is_banned INTEGER DEFAULT 0,
        downloads_today INTEGER DEFAULT 0,
        last_reset_date TEXT,
        joined_at TEXT
    );
    """)
    conn.commit()
    conn.close()


def today():
    return datetime.date.today().isoformat()


def get_or_create_user(telegram_id: int, username: str | None):
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,)).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO users (telegram_id, username, last_reset_date, joined_at) VALUES (?, ?, ?, ?)",
            (telegram_id, username, today(), datetime.datetime.utcnow().isoformat()),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,)).fetchone()
    conn.close()
    return row


def update_user(telegram_id: int, **fields):
    if not fields:
        return
    conn = get_conn()
    set_clause = ", ".join(f"{k}=?" for k in fields)
    conn.execute(f"UPDATE users SET {set_clause} WHERE telegram_id=?", (*fields.values(), telegram_id))
    conn.commit()
    conn.close()


def get_user(telegram_id: int):
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,)).fetchone()
    conn.close()
    return row


def reset_quota_if_new_day(telegram_id: int):
    user = get_user(telegram_id)
    if user and user["last_reset_date"] != today():
        update_user(telegram_id, downloads_today=0, last_reset_date=today())


def increment_download_count(telegram_id: int):
    conn = get_conn()
    conn.execute("UPDATE users SET downloads_today = downloads_today + 1 WHERE telegram_id=?", (telegram_id,))
    conn.commit()
    conn.close()


def all_active_user_ids():
    conn = get_conn()
    rows = conn.execute("SELECT telegram_id FROM users WHERE is_banned=0").fetchall()
    conn.close()
    return [r["telegram_id"] for r in rows]


def stats():
    conn = get_conn()
    total = conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
    vip = conn.execute("SELECT COUNT(*) c FROM users WHERE is_vip=1").fetchone()["c"]
    banned = conn.execute("SELECT COUNT(*) c FROM users WHERE is_banned=1").fetchone()["c"]
    conn.close()
    return {"total": total, "vip": vip, "banned": banned}
