import os
import re
import uuid
import yt_dlp

MAX_FILE_MB = int(os.getenv("MAX_FILE_MB", "500"))
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# مسیر فایل کوکی. Render فایل‌های Secret File رو تو /etc/secrets/<filename> مانت می‌کنه،
# نه کنار خود کد - قبلاً همینجا اشتباه بود و باعث می‌شد کوکی اصلاً پیدا نشه.
COOKIES_PATH = os.getenv("COOKIES_PATH", "/etc/secrets/cookies.txt")

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


def _extra_opts() -> dict:
    """
    تنظیمات مشترک برای دور زدن محدودیت‌های یوتیوب روی آی‌پی سرورهای ابری:
    - کوکی یه اکانت واقعی (اگه فایلش موجود باشه)
    - کلاینت android_vr در اولویت اول: در حال حاضر بهترین راه برای گرفتن کیفیت‌های
      720/1080 بدون نیاز به تایید امنیتی یا لاگین
    """
    opts = {
        "nocheckcertificate": True,
        "extractor_args": {"youtube": {"player_client": ["android_vr", "tvhtml5", "android"]}},
        "http_headers": {"User-Agent": USER_AGENT},
    }
    if os.path.exists(COOKIES_PATH):
        opts["cookiefile"] = COOKIES_PATH
    return opts


YOUTUBE_REGEX = re.compile(
    r"(youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/)"
)


def is_youtube_url(text: str) -> bool:
    return bool(YOUTUBE_REGEX.search(text or ""))


def fetch_formats(url: str):
    """
    اطلاعات ویدیو و لیست کوتاهی از کیفیت‌های قابل‌انتخاب (خودمون فیلترش می‌کنیم
    تا فقط چند گزینه‌ی معنادار به کاربر نشون بدیم، نه ده‌ها فرمت خام).
    """
    ydl_opts = {"quiet": True, "skip_download": True, "noplaylist": True, **_extra_opts()}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        print(f"[fetch_formats error] {e}")
        raise

    title = info.get("title", "video")
    duration = info.get("duration", 0)

    wanted_heights = [360, 480, 720, 1080]
    available = []
    seen = set()
    for f in info.get("formats", []):
        h = f.get("height")
        if h in wanted_heights and f.get("vcodec") != "none" and h not in seen:
            size = f.get("filesize") or f.get("filesize_approx")
            available.append({"height": h, "format_id": f["format_id"], "size_mb": (size / 1_048_576) if size else None})
            seen.add(h)

    available.sort(key=lambda x: x["height"])
    return {"title": title, "duration": duration, "qualities": available}


def download_video(url: str, height: int | None) -> tuple[str | None, str]:
    """
    height=None یعنی فقط صدا (MP3). برمی‌گردونه (مسیر_فایل یا None, پیام_خطا).
    """
    file_id = uuid.uuid4().hex[:8]
    outtmpl = os.path.join(DOWNLOAD_DIR, f"{file_id}.%(ext)s")

    if height is None:
        ydl_opts = {
            "quiet": True,
            "noplaylist": True,
            "format": "bestaudio/best",
            "outtmpl": outtmpl,
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }],
            "max_filesize": MAX_FILE_MB * 1_048_576,
            **_extra_opts(),
        }
    else:
        ydl_opts = {
            "quiet": True,
            "noplaylist": True,
            "format": f"bestvideo[height<={height}]+bestaudio/best[height<={height}]",
            "merge_output_format": "mp4",
            "outtmpl": outtmpl,
            "max_filesize": MAX_FILE_MB * 1_048_576,
            **_extra_opts(),
        }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except yt_dlp.utils.DownloadError as e:
        print(f"[download_video error] {e}")
        if "max-filesize" in str(e).lower() or "File is larger" in str(e):
            return None, "too_large"
        return None, "error"
    except Exception as e:
        print(f"[download_video error] {e}")
        return None, "error"

    # پیدا کردن فایل خروجی واقعی (چون پسوند نهایی از قبل معلوم نیست)
    for fname in os.listdir(DOWNLOAD_DIR):
        if fname.startswith(file_id):
            full_path = os.path.join(DOWNLOAD_DIR, fname)
            size_mb = os.path.getsize(full_path) / 1_048_576
            if size_mb > MAX_FILE_MB:
                os.remove(full_path)
                return None, "too_large"
            return full_path, "ok"

    return None, "error"


def cleanup(path: str):
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except Exception:
        pass
