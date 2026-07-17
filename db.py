import os
import datetime
import psycopg2
import psycopg2.extras

# آدرس اتصال به دیتابیس Postgres (از Neon یا Supabase می‌گیری)
# باید به صورت Environment Variable با اسم DATABASE_URL ست بشه
DATABASE_URL = os.environ["DATABASE_URL"]


def get_conn():
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    return conn


def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        telegram_id BIGINT PRIMARY KEY,
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
    cur.close()
    conn.close()


def today():
    return datetime.date.today().isoformat()


def get_or_create_user(telegram_id: int, username):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE telegram_id=%s", (telegram_id,))
    row = cur.fetchone()
    if row is None:
        cur.execute(
            "INSERT INTO users (telegram_id, username, last_reset_date, joined_at) VALUES (%s, %s, %s, %s)",
            (telegram_id, username, today(), datetime.datetime.utcnow().isoformat()),
        )
        conn.commit()
        cur.execute("SELECT * FROM users WHERE telegram_id=%s", (telegram_id,))
        row = cur.fetchone()
    cur.close()
    conn.close()
    return row


def update_user(telegram_id: int, **fields):
    if not fields:
        return
    conn = get_conn()
    cur = conn.cursor()
    set_clause = ", ".join(f"{k}=%s" for k in fields)
    cur.execute(f"UPDATE users SET {set_clause} WHERE telegram_id=%s", (*fields.values(), telegram_id))
    conn.commit()
    cur.close()
    conn.close()


def get_user(telegram_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE telegram_id=%s", (telegram_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row


def reset_quota_if_new_day(telegram_id: int):
    user = get_user(telegram_id)
    if user and user["last_reset_date"] != today():
        update_user(telegram_id, downloads_today=0, last_reset_date=today())


def increment_download_count(telegram_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE users SET downloads_today = downloads_today + 1 WHERE telegram_id=%s", (telegram_id,))
    conn.commit()
    cur.close()
    conn.close()


def all_active_user_ids():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT telegram_id FROM users WHERE is_banned=0")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [r["telegram_id"] for r in rows]


def stats():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) c FROM users")
    total = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) c FROM users WHERE is_vip=1")
    vip = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) c FROM users WHERE is_banned=1")
    banned = cur.fetchone()["c"]
    cur.close()
    conn.close()
    return {"total": total, "vip": vip, "banned": banned}
