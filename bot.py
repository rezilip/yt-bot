# -*- coding: utf-8 -*-
import os
import html
from dotenv import load_dotenv
import telebot
from telebot import types

import db
import i18n
import downloader

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME")
CHANNEL_LINK = os.getenv("CHANNEL_LINK")
FREE_DAILY_LIMIT = int(os.getenv("FREE_DAILY_LIMIT", "5"))
SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME", "@irezafattahi")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")


def esc(text) -> str:
    """
    هر متنی که از بیرون میاد (عنوان ویدیو، پیام کاربر، اسم کاربر) قبل از قرار گرفتن
    تو پیام HTML باید escape بشه، وگرنه اگه شامل &, <, > باشه تلگرام کل پیام رو
    رد می‌کنه و کاربر هیچ پاسخی نمی‌بینه.
    """
    return html.escape(str(text or ""))
db.init_db()

pending_video = {}   # telegram_id -> {"url":..., "title":..., "qualities":[...]}
user_state = {}       # telegram_id -> "awaiting_broadcast"


def L(uid: int) -> str:
    user = db.get_user(uid)
    return (user["language"] if user and user["language"] else "en")


def is_admin(uid: int) -> bool:
    return uid in ADMIN_IDS


def is_member(uid: int) -> bool:
    try:
        member = bot.get_chat_member(CHANNEL_USERNAME, uid)
        return member.status not in ("left", "kicked")
    except Exception:
        return False


# ---------- کیبوردها ----------

def language_kb():
    kb = types.InlineKeyboardMarkup()
    for code in i18n.LANGS:
        kb.add(types.InlineKeyboardButton(i18n.LANG_NAMES[code], callback_data=f"setlang:{code}"))
    return kb


def join_kb(lang):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton(i18n.t("join_button", lang), url=CHANNEL_LINK))
    kb.add(types.InlineKeyboardButton(i18n.t("check_join_button", lang), callback_data="check_join"))
    return kb


def main_menu_kb(lang):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(i18n.t("menu_download", lang))
    kb.row(i18n.t("menu_vip", lang), i18n.t("menu_support", lang))
    kb.row(i18n.t("menu_donate", lang), i18n.t("menu_help", lang))
    kb.row(i18n.t("menu_language", lang))
    return kb


# ---------- گیت ورودی: عضویت کانال ----------

def gate_ok(uid: int) -> bool:
    lang = L(uid)
    if not is_member(uid):
        bot.send_message(uid, i18n.t("join_required", lang), reply_markup=join_kb(lang))
        return False
    user = db.get_user(uid)
    if user and user["is_banned"]:
        bot.send_message(uid, i18n.t("banned", lang))
        return False
    return True


# ---------- شروع + انتخاب زبان ----------

@bot.message_handler(commands=["start"])
def cmd_start(message):
    uid = message.from_user.id
    user = db.get_or_create_user(uid, message.from_user.username)

    if not user["language"]:
        bot.send_message(uid, i18n.t("choose_language", "en"), reply_markup=language_kb())
        return

    lang = user["language"]
    if not is_member(uid):
        bot.send_message(uid, i18n.t("join_required", lang), reply_markup=join_kb(lang))
        return

    bot.send_message(uid, i18n.t("welcome", lang), reply_markup=main_menu_kb(lang))


@bot.callback_query_handler(func=lambda c: c.data.startswith("setlang:"))
def cb_setlang(call):
    uid = call.from_user.id
    lang = call.data.split(":")[1]
    db.update_user(uid, language=lang)
    bot.delete_message(uid, call.message.message_id)
    bot.send_message(uid, i18n.t("language_set", lang))

    if not is_member(uid):
        bot.send_message(uid, i18n.t("join_required", lang), reply_markup=join_kb(lang))
        return
    bot.send_message(uid, i18n.t("welcome", lang), reply_markup=main_menu_kb(lang))


@bot.callback_query_handler(func=lambda c: c.data == "check_join")
def cb_check_join(call):
    uid = call.from_user.id
    lang = L(uid)
    if is_member(uid):
        bot.delete_message(uid, call.message.message_id)
        bot.send_message(uid, i18n.t("welcome", lang), reply_markup=main_menu_kb(lang))
    else:
        bot.answer_callback_query(call.id, i18n.t("not_member_yet", lang), show_alert=True)


@bot.message_handler(func=lambda m: m.text in [i18n.t("menu_language", c) for c in i18n.LANGS])
def change_language(message):
    bot.send_message(message.from_user.id, i18n.t("choose_language", L(message.from_user.id)), reply_markup=language_kb())


# ---------- دانلود یوتیوب ----------

@bot.message_handler(func=lambda m: m.text in [i18n.t("menu_download", c) for c in i18n.LANGS])
def ask_for_link(message):
    uid = message.from_user.id
    if not gate_ok(uid):
        return
    bot.send_message(uid, i18n.t("send_link_prompt", L(uid)))


@bot.message_handler(func=lambda m: downloader.is_youtube_url(m.text))
def handle_youtube_link(message):
    uid = message.from_user.id
    lang = L(uid)
    if not gate_ok(uid):
        return

    db.reset_quota_if_new_day(uid)
    user = db.get_user(uid)
    if not user["is_vip"] and user["downloads_today"] >= FREE_DAILY_LIMIT:
        bot.send_message(uid, i18n.t("quota_reached", lang))
        return

    bot.send_message(uid, i18n.t("fetching_info", lang))
    try:
        info = downloader.fetch_formats(message.text.strip())
    except Exception:
        bot.send_message(uid, i18n.t("download_error", lang))
        return

    pending_video[uid] = {"url": message.text.strip(), **info}

    kb = types.InlineKeyboardMarkup()
    for q in info["qualities"]:
        size_txt = f" (~{q['size_mb']:.0f}MB)" if q["size_mb"] else ""
        kb.add(types.InlineKeyboardButton(f"🎞 {q['height']}p{size_txt}", callback_data=f"dl:{q['height']}"))
    kb.add(types.InlineKeyboardButton("🎵 MP3", callback_data="dl:audio"))

    bot.send_message(uid, f"<b>{esc(info['title'])}</b>\n\n{i18n.t('choose_quality', lang)}", reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data.startswith("dl:"))
def cb_download(call):
    uid = call.from_user.id
    lang = L(uid)
    if uid not in pending_video:
        return

    choice = call.data.split(":")[1]
    height = None if choice == "audio" else int(choice)

    bot.answer_callback_query(call.id)
    bot.send_message(uid, i18n.t("downloading", lang))

    url = pending_video[uid]["url"]
    path, status = downloader.download_video(url, height)

    if status == "too_large":
        bot.send_message(uid, i18n.t("file_too_large", lang))
        return
    if status != "ok" or not path:
        bot.send_message(uid, i18n.t("download_error", lang))
        return

    try:
        with open(path, "rb") as f:
            if height is None:
                bot.send_audio(uid, f)
            else:
                bot.send_video(uid, f, supports_streaming=True)
        db.increment_download_count(uid)
        bot.send_message(uid, i18n.t("download_done", lang))
    except Exception:
        bot.send_message(uid, i18n.t("download_error", lang))
    finally:
        downloader.cleanup(path)
        pending_video.pop(uid, None)


# ---------- VIP / پشتیبانی / دونیت / راهنما ----------

@bot.message_handler(func=lambda m: m.text in [i18n.t("menu_vip", c) for c in i18n.LANGS])
def vip_status(message):
    uid = message.from_user.id
    if not gate_ok(uid):
        return
    lang = L(uid)
    user = db.get_user(uid)
    key = "vip_status_vip" if user["is_vip"] else "vip_status_free"
    bot.send_message(uid, i18n.t(key, lang))


@bot.message_handler(func=lambda m: m.text in [i18n.t("menu_support", c) for c in i18n.LANGS])
def support(message):
    uid = message.from_user.id
    if not gate_ok(uid):
        return
    bot.send_message(uid, i18n.t("support_text", L(uid)))


@bot.message_handler(func=lambda m: m.text in [i18n.t("menu_donate", c) for c in i18n.LANGS])
def donate(message):
    uid = message.from_user.id
    if not gate_ok(uid):
        return
    bot.send_message(uid, i18n.t("donate_text", L(uid)))


@bot.message_handler(func=lambda m: m.text in [i18n.t("menu_help", c) for c in i18n.LANGS])
def help_cmd(message):
    uid = message.from_user.id
    if not gate_ok(uid):
        return
    bot.send_message(uid, i18n.t("help_text", L(uid)))


# ================= پنل ادمین =================

@bot.message_handler(commands=["admin"])
def admin_panel(message):
    if not is_admin(message.from_user.id):
        return
    bot.send_message(
        message.from_user.id,
        "🛠 <b>پنل ادمین</b>\n\n"
        "<code>/stats</code> — آمار کلی\n"
        "<code>/vip آیدی</code> — VIP کردن کاربر\n"
        "<code>/unvip آیدی</code> — حذف VIP\n"
        "<code>/ban آیدی</code> — مسدود کردن\n"
        "<code>/unban آیدی</code> — رفع مسدودی\n"
        "<code>/broadcast متن</code> — پیام همگانی",
    )


@bot.message_handler(commands=["stats"])
def admin_stats(message):
    if not is_admin(message.from_user.id):
        return
    s = db.stats()
    bot.send_message(message.from_user.id, f"👥 کل: {s['total']}\n👑 VIP: {s['vip']}\n🚫 مسدود: {s['banned']}")


@bot.message_handler(commands=["vip", "unvip", "ban", "unban"])
def admin_actions(message):
    if not is_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) != 2:
        bot.send_message(message.from_user.id, "فرمت: /vip آیدی_عددی")
        return
    target = int(parts[1])
    cmd = parts[0].replace("/", "")
    field_map = {
        "vip": {"is_vip": 1}, "unvip": {"is_vip": 0},
        "ban": {"is_banned": 1}, "unban": {"is_banned": 0},
    }
    db.update_user(target, **field_map[cmd])
    bot.send_message(message.from_user.id, "انجام شد ✅")


@bot.message_handler(commands=["broadcast"])
def admin_broadcast(message):
    if not is_admin(message.from_user.id):
        return
    text = message.text.replace("/broadcast", "", 1).strip()
    if not text:
        bot.send_message(message.from_user.id, "فرمت: /broadcast متن پیام")
        return
    sent = 0
    for uid in db.all_active_user_ids():
        try:
            bot.send_message(uid, text)
            sent += 1
        except Exception:
            pass
    bot.send_message(message.from_user.id, f"برای {sent} کاربر ارسال شد ✅")


def start_polling():
    import time
    while True:
        try:
            bot.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=30)
        except Exception as e:
            print(f"[polling crashed, retrying in 10s] {e}")
            time.sleep(10)
