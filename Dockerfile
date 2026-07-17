FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg curl unzip ca-certificates git nodejs npm && rm -rf /var/lib/apt/lists/*

# نصب Deno: از اواخر ۲۰۲۵، یوتیوب یه چالش جاوااسکریپتی (signature/n) اضافه کرده
# که yt-dlp برای باز کردن لینک واقعی ویدیو لازمش داره. بدون این، فقط فرمت‌های
# عکس در دسترس می‌مونن و دانلود با "Requested format is not available" فیل می‌شه.
RUN curl -fsSL https://deno.land/install.sh | sh \
    && cp /root/.deno/bin/deno /usr/local/bin/deno \
    && chmod 755 /usr/local/bin/deno \
    && deno --version

# نصب bgutil-ytdlp-pot-provider: تولیدکننده‌ی PO Token. یوتیوب الان برای دادن
# لینک کیفیت‌های واقعی (نه فقط SABR/تصویر) به این توکن نیاز داره. این یه اسکریپت
# Node.js‌ه که هر بار که yt-dlp لازم داشته باشه، صداش می‌کنه (نیازی به سرور
# دائمی جدا نیست).
RUN git clone --depth 1 --branch 1.3.1 https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git /opt/bgutil-ytdlp-pot-provider \
    && cd /opt/bgutil-ytdlp-pot-provider/server \
    && npm ci \
    && npx tsc

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

ENV PORT=10000
EXPOSE 10000

CMD ["gunicorn", "-w", "1", "-b", "0.0.0.0:10000", "app:app"]
