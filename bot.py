import os
import re
import requests
import asyncio
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, time
import pytz
from PIL import Image

from telegram import Bot

# === تنظیمات ثابت ===
SOURCE1_HASHTAG = "#خبرنامه_افسران"
TARGET_CAPTION = "♨️ امروز در ایران و جهان چه گذشت؟\nمنتخب مهم‌ترین اخبار ۲۴ ساعت گذشته\n\nبرای دسترسی به شماره‌های قبلی این خبرنامه، هشتگ زیر را لمس کنید:\n#خبرنامه@SumsTweetMD"

# === دریافت متغیرهای محیطی (secrets) ===
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
SOURCE_CHANNEL_1 = os.getenv("SOURCE_CHANNEL_1")
TARGET_CHANNEL = os.getenv("TARGET_CHANNEL")

# مسیر فایل overlay (تصویر PNG که قرار است روی تصویر دانلود شده قرار بگیرد)
OVERLAY_IMAGE_PATH = "overlay.png"

# === تنظیم منطقه زمانی تهران ===
tehran_tz = pytz.timezone("Asia/Tehran")
now_tehran = datetime.now(tehran_tz)
today_date = now_tehran.date()
yesterday_date = today_date - timedelta(days=1)
start_time = tehran_tz.localize(datetime.combine(yesterday_date, time(22, 0)))
# تغییر پایان بازه به 00:01 امروز (به وقت تهران)
end_time = tehran_tz.localize(datetime.combine(today_date, time(0, 1)))

def parse_datetime(datetime_str):
    """
    تبدیل رشته تاریخ (ISO 8601) به شیء datetime در منطقه زمانی تهران.
    """
    try:
        dt = datetime.fromisoformat(datetime_str)
        result = dt.astimezone(tehran_tz)
        print(f"[INFO] Parsed datetime: {result}")
        return result
    except Exception as e:
        print(f"[ERROR] در parse_datetime: {e}")
        return None

def scrape_channel(channel_username, required_hashtag):
    """
    وب‌اسکرپینگ یک کانال public تلگرام برای یافتن اولین پستی در بازه زمانی مشخص
    که در کپشنش هشتگ مورد نظر (required_hashtag) وجود دارد.
    
    در صورت یافتن، تصویر پست دانلود شده و مسیر فایل تصویر برگردانده می‌شود.
    در غیر این صورت None برگردانده می‌شود.
    """
    url = f"https://t.me/s/{channel_username.strip('@')}"
    print(f"[INFO] در حال اسکرپ کردن کانال: {url}")
    try:
        response = requests.get(url)
    except Exception as e:
        print(f"[ERROR] درخواست به {url} با خطا مواجه شد: {e}")
        return None

    if response.status_code != 200:
        print(f"[ERROR] دریافت صفحه {url} با وضعیت {response.status_code} مواجه شد.")
        return None
    soup = BeautifulSoup(response.text, "html.parser")
    
    posts = soup.find_all("div", class_="tgme_widget_message_wrap")
    print(f"[INFO] تعداد پست‌های یافت شده: {len(posts)}")
    for post in posts:
        time_tag = post.find("time")
        if time_tag and time_tag.has_attr("datetime"):
            post_time = parse_datetime(time_tag["datetime"])
            if post_time is None:
                continue
            if not (start_time <= post_time <= end_time):
                print(f"[DEBUG] پست با زمان {post_time} خارج از بازه مشخص شده است.")
                continue
        else:
            print("[DEBUG] پست فاقد تگ زمان است.")
            continue

        caption_div = post.find("div", class_="tgme_widget_message_text")
        caption_text = caption_div.get_text() if caption_div else ""
        print(f"[DEBUG] کپشن پست: {caption_text}")
        if required_hashtag not in caption_text:
            print(f"[DEBUG] هشتگ {required_hashtag} در کپشن موجود نیست.")
            continue

        photo_wrap = post.find("a", class_="tgme_widget_message_photo_wrap")
        if photo_wrap and photo_wrap.has_attr("style"):
            style = photo_wrap["style"]
            match = re.search(r"url\('(.*?)'\)", style)
            if match:
                image_url = match.group(1)
                print(f"[INFO] آدرس تصویر پیدا شده: {image_url}")
                try:
                    img_response = requests.get(image_url)
                except Exception as e:
                    print(f"[ERROR] دانلود تصویر با خطا مواجه شد: {e}")
                    continue
                if img_response.status_code == 200:
                    file_path = f"{channel_username.strip('@')}_image.jpg"
                    try:
                        with open(file_path, "wb") as f:
                            f.write(img_response.content)
                        print(f"[INFO] تصویر دانلود شده در: {file_path}")
                        return file_path
                    except Exception as e:
                        print(f"[ERROR] ذخیره تصویر با خطا مواجه شد: {e}")
                        return None
    print("[INFO] هیچ پستی با مشخصات داده شده یافت نشد.")
    return None

def composite_image(base_image_path, overlay_image_path):
    """
    ترکیب تصویر دانلود شده (base_image) با تصویر overlay (PNG) که شامل بخش‌های transparent است.
    تصویر overlay در صورت نیاز به اندازه‌ی base_image تغییر اندازه داده می‌شود.
    نتیجه در فایلی به نام "final_<base_image_name>.png" ذخیره می‌شود.
    """
    try:
        print(f"[INFO] ترکیب تصویر {base_image_path} با overlay {overlay_image_path}")
        base_img = Image.open(base_image_path).convert("RGBA")
        overlay_img = Image.open(overlay_image_path).convert("RGBA")
        if overlay_img.size != base_img.size:
            print(f"[DEBUG] تغییر اندازه overlay از {overlay_img.size} به {base_img.size}")
            # استفاده از فیلتر LANCZOS برای کیفیت بهتر در تغییر اندازه
            overlay_img = overlay_img.resize(base_img.size, resample=Image.LANCZOS)
        final_img = Image.alpha_composite(base_img, overlay_img)
        # تعیین نام فایل نهایی با پسوند png
        final_image_path = f"final_{os.path.splitext(os.path.basename(base_image_path))[0]}.png"
        # ذخیره تصویر نهایی به صورت PNG (بدون فشرده‌سازی اتلافی)
        final_img.save(final_image_path, format="PNG", optimize=True)
        print(f"[INFO] تصویر نهایی ذخیره شد: {final_image_path}")
        return final_image_path
    except Exception as e:
        print(f"[ERROR] در composite_image: {e}")
        return base_image_path

async def send_photo(image_path):
    """
    ارسال یک تصویر به کانال مقصد با استفاده از متد send_photo.
    از async context manager برای مدیریت Bot استفاده می‌شود.
    """
    print(f"[INFO] آماده ارسال تصویر: {image_path} به کانال {TARGET_CHANNEL}")
    try:
        async with Bot(token=TELEGRAM_BOT_TOKEN) as bot:
            with open(image_path, "rb") as photo_file:
                await bot.send_photo(chat_id=TARGET_CHANNEL, photo=photo_file, caption=TARGET_CAPTION)
        print("[INFO] تصویر با موفقیت ارسال شد.")
    except Exception as e:
        print(f"[ERROR] ارسال تصویر با خطا مواجه شد: {e}")

async def main():
    print("[INFO] اجرای برنامه آغاز شد.")
    image_path = scrape_channel(SOURCE_CHANNEL_1, SOURCE1_HASHTAG)
    if image_path:
        final_image_path = composite_image(image_path, OVERLAY_IMAGE_PATH)
        await send_photo(final_image_path)
    else:
        print("[INFO] تصویر مورد نظر پیدا نشد؛ بنابراین عملی انجام نخواهد شد.")

if __name__ == "__main__":
    asyncio.run(main())
