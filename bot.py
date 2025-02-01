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
end_time = tehran_tz.localize(datetime.combine(today_date, time(1, 0)))

def parse_datetime(datetime_str):
    """
    تبدیل رشته تاریخ (ISO 8601) به شیء datetime در منطقه زمانی تهران.
    """
    dt = datetime.fromisoformat(datetime_str)
    return dt.astimezone(tehran_tz)

def scrape_channel(channel_username, required_hashtag):
    """
    وب‌اسکرپینگ یک کانال public تلگرام برای یافتن اولین پستی در بازه زمانی مشخص
    که در کپشنش هشتگ مورد نظر (required_hashtag) وجود دارد.
    
    در صورت یافتن، تصویر پست دانلود شده و مسیر فایل تصویر برگردانده می‌شود.
    در غیر این صورت None برگردانده می‌شود.
    """
    url = f"https://t.me/s/{channel_username.strip('@')}"
    response = requests.get(url)
    if response.status_code != 200:
        return None
    soup = BeautifulSoup(response.text, "html.parser")
    
    # یافتن تمامی پست‌ها؛ ساختار HTML صفحه کانال ممکن است تغییر کند
    posts = soup.find_all("div", class_="tgme_widget_message_wrap")
    for post in posts:
        # استخراج زمان ارسال پست
        time_tag = post.find("time")
        if time_tag and time_tag.has_attr("datetime"):
            post_time = parse_datetime(time_tag["datetime"])
            if not (start_time <= post_time <= end_time):
                continue
        else:
            continue

        # بررسی وجود هشتگ مورد نظر در کپشن
        caption_div = post.find("div", class_="tgme_widget_message_text")
        caption_text = caption_div.get_text() if caption_div else ""
        if required_hashtag not in caption_text:
            continue

        # استخراج لینک تصویر؛ بررسی المان عکس
        photo_wrap = post.find("a", class_="tgme_widget_message_photo_wrap")
        if photo_wrap and photo_wrap.has_attr("style"):
            style = photo_wrap["style"]
            match = re.search(r"url\('(.*?)'\)", style)
            if match:
                image_url = match.group(1)
                # دانلود تصویر
                img_response = requests.get(image_url)
                if img_response.status_code == 200:
                    file_path = f"{channel_username.strip('@')}_image.jpg"
                    with open(file_path, "wb") as f:
                        f.write(img_response.content)
                    return file_path
    return None

def composite_image(base_image_path, overlay_image_path):
    """
    ترکیب تصویر دانلود شده (base_image) با تصویر overlay (PNG) که شامل بخش‌های transparent است.
    تصویر overlay در صورت نیاز به اندازه‌ی base_image تغییر اندازه داده می‌شود.
    نتیجه در فایلی به نام "final_<base_image_name>" ذخیره می‌شود.
    """
    try:
        base_img = Image.open(base_image_path).convert("RGBA")
        overlay_img = Image.open(overlay_image_path).convert("RGBA")
        # در صورت عدم تطابق ابعاد، تغییر اندازه overlay به ابعاد base_img
        if overlay_img.size != base_img.size:
            overlay_img = overlay_img.resize(base_img.size)
        # ترکیب دو تصویر
        final_img = Image.alpha_composite(base_img, overlay_img)
        final_image_path = f"final_{os.path.basename(base_image_path)}"
        final_img.save(final_image_path)
        return final_image_path
    except Exception as e:
        print(f"Error during compositing image: {e}")
        return base_image_path  # در صورت بروز خطا، تصویر اصلی را برمی‌گرداند

async def send_photo(image_path):
    """
    ارسال یک تصویر به کانال مقصد با استفاده از متد send_photo.
    """
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    with open(image_path, "rb") as photo_file:
        await bot.send_photo(chat_id=TARGET_CHANNEL, photo=photo_file, caption=TARGET_CAPTION)

async def main():
    # پردازش فقط کانال مبدا اول با هشتگ مربوطه
    image_path = scrape_channel(SOURCE_CHANNEL_1, SOURCE1_HASHTAG)
    if image_path:
        # ترکیب تصویر دانلود شده با overlay
        final_image_path = composite_image(image_path, OVERLAY_IMAGE_PATH)
        await send_photo(final_image_path)
    # در صورت عدم یافتن تصویر، هیچ عملی انجام نخواهد شد.

if __name__ == "__main__":
    asyncio.run(main())
