import os
import re
import requests
import asyncio
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, time
import pytz

from telegram import InputMediaPhoto, Bot

# === تنظیمات ثابت ===
FIXED_HASHTAG = "#YourHashtag"         # هشتگ ثابت؛ به مقدار دلخواه تغییر دهید
TARGET_CAPTION = "کپشن دلخواه شما"     # کپشن دلخواه برای ارسال در کانال مقصد

# === دریافت متغیرهای محیطی (secrets) ===
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
SOURCE_CHANNEL_1 = os.getenv("SOURCE_CHANNEL_1")
SOURCE_CHANNEL_2 = os.getenv("SOURCE_CHANNEL_2")
TARGET_CHANNEL = os.getenv("TARGET_CHANNEL")

# === تنظیم منطقه زمانی تهران ===
tehran_tz = pytz.timezone("Asia/Tehran")
now_tehran = datetime.now(tehran_tz)
today_date = now_tehran.date()
# تعریف بازه زمانی: از 22:00 روز قبل تا 01:00 امروز (همه به وقت تهران)
yesterday_date = today_date - timedelta(days=1)
start_time = tehran_tz.localize(datetime.combine(yesterday_date, time(22, 0)))
end_time = tehran_tz.localize(datetime.combine(today_date, time(1, 0)))

def parse_datetime(datetime_str):
    """
    تبدیل رشته تاریخ (ISO 8601) به شیء datetime در منطقه زمانی تهران.
    """
    dt = datetime.fromisoformat(datetime_str)
    return dt.astimezone(tehran_tz)

def scrape_channel(channel_username):
    """
    وب‌اسکرپینگ یک کانال public تلگرام برای یافتن اولین پستی در بازه زمانی مشخص
    که در کپشنش هشتگ ثابت وجود دارد.
    
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

        # بررسی وجود هشتگ ثابت در کپشن
        caption_div = post.find("div", class_="tgme_widget_message_text")
        caption_text = caption_div.get_text() if caption_div else ""
        if FIXED_HASHTAG not in caption_text:
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

async def send_group_media(image_paths):
    """
    ارسال تصاویر موجود (یکی یا هر دو) به صورت گروهی (media group) به کانال مقصد.
    در صورتی که هر دو تصویر موجود باشند، تنها روی اولین عکس کپشن اعمال می‌شود.
    """
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    media = []
    # اگر حداقل یک تصویر موجود باشد، کپشن به اولین عکس اضافه می‌شود
    for idx, path in enumerate(image_paths):
        # باز کردن فایل‌ها؛ دقت کنید که این فایل‌ها پس از ارسال توسط ربات بسته می‌شوند.
        file_obj = open(path, "rb")
        if idx == 0:
            media.append(InputMediaPhoto(file_obj, caption=TARGET_CAPTION))
        else:
            media.append(InputMediaPhoto(file_obj))
    if media:
        await bot.send_media_group(chat_id=TARGET_CHANNEL, media=media)
    # بستن فایل‌های باز شده (در صورت لزوم)
    for item in media:
        try:
            item.media.close()
        except Exception:
            pass

async def main():
    image_paths = []
    # پردازش هر دو کانال منبع
    for channel in [SOURCE_CHANNEL_1, SOURCE_CHANNEL_2]:
        path = scrape_channel(channel)
        if path:
            image_paths.append(path)
    # حتی اگر تنها یک تصویر موجود باشد، عملیات ارسال ادامه می‌یابد.
    await send_group_media(image_paths)

if __name__ == "__main__":
    asyncio.run(main())
