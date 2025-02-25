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
TARGET_CAPTION = ("♨️ امروز در ایران و جهان چه گذشت؟\n"
                  "منتخب مهم‌ترین اخبار ۲۴ ساعت گذشته\n\n"
                  "برای دسترسی به شماره‌های قبلی این خبرنامه، هشتگ زیر را لمس کنید:\n"
                  "#خبرنامه@SumsTweetMD")

# === دریافت متغیرهای محیطی ===
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
SOURCE_CHANNEL_1 = os.getenv("SOURCE_CHANNEL_1")
TARGET_CHANNEL = os.getenv("TARGET_CHANNEL")

# === تنظیم منطقه زمانی تهران ===
tehran_tz = pytz.timezone("Asia/Tehran")
now_tehran = datetime.now(tehran_tz)
today_date = now_tehran.date()
yesterday_date = today_date - timedelta(days=1)
base_start_time = tehran_tz.localize(datetime.combine(yesterday_date, time(20, 0)))

CROP_HEIGHT = 224  # مقدار پیکسلی که از بالای تصویر کراپ می‌شود

def scrape_channel(channel_username, start_time_range, end_time_range):
    url = f"https://t.me/s/{channel_username.strip('@')}"
    print(f"[INFO] در حال اسکرپ کردن کانال: {url}")
    try:
        response = requests.get(url)
        response.raise_for_status()
    except Exception as e:
        print(f"[ERROR] درخواست به {url} با خطا مواجه شد: {e}")
        return None

    soup = BeautifulSoup(response.text, "html.parser")
    posts = soup.find_all("div", class_="tgme_widget_message_wrap")
    print(f"[INFO] تعداد پست‌های یافت شده: {len(posts)}")
    
    for post in posts:
        time_tag = post.find("time")
        if time_tag and time_tag.has_attr("datetime"):
            try:
                post_time = datetime.fromisoformat(time_tag["datetime"]).astimezone(tehran_tz)
            except Exception as e:
                print(f"[ERROR] در تبدیل زمان: {e}")
                continue
            if not (start_time_range <= post_time <= end_time_range):
                print(f"[DEBUG] پست با زمان {post_time} خارج از بازه مشخص شده است.")
                continue
        else:
            print("[DEBUG] پست فاقد تگ زمان است.")
            continue

        # بررسی وجود هشتگ مورد نظر در کپشن
        caption_div = post.find("div", class_="tgme_widget_message_text")
        caption_text = caption_div.get_text() if caption_div else ""
        if SOURCE1_HASHTAG not in caption_text:
            print(f"[DEBUG] هشتگ {SOURCE1_HASHTAG} در کپشن موجود نیست.")
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
                    img_response.raise_for_status()
                    file_path = "downloaded_image.jpg"
                    with open(file_path, "wb") as f:
                        f.write(img_response.content)
                    print(f"[INFO] تصویر دانلود شده در: {file_path}")
                    return file_path
                except Exception as e:
                    print(f"[ERROR] دانلود تصویر با خطا مواجه شد: {e}")
    print("[INFO] هیچ پستی با مشخصات داده شده یافت نشد.")
    return None

def crop_image(image_path, crop_height):
    try:
        img = Image.open(image_path)
        width, height = img.size
        cropped_img = img.crop((0, crop_height, width, height))
        cropped_path = "cropped_image.png"
        cropped_img.save(cropped_path, format="PNG", optimize=True)
        print(f"[INFO] تصویر پس از کراپ در: {cropped_path}")
        return cropped_path
    except Exception as e:
        print(f"[ERROR] در برش تصویر: {e}")
        return image_path

async def send_photo(cropped_path):
    try:
        async with Bot(token=TELEGRAM_BOT_TOKEN) as bot:
            with open(cropped_path, "rb") as photo_file:
                await bot.send_photo(chat_id=TARGET_CHANNEL, photo=photo_file, caption=TARGET_CAPTION)
        print("[INFO] تصویر کراپ شده ارسال شد.")
    except Exception as e:
        print(f"[ERROR] ارسال تصویر با خطا مواجه شد: {e}")

async def main():
    stop_time = tehran_tz.localize(datetime.combine(today_date, time(3, 2)))
    attempt = 0
    image_path = None

    while True:
        attempt += 1
        current_time = datetime.now(tehran_tz)
        print(f"[INFO] تلاش {attempt}: بازه جستجو از {base_start_time} تا {current_time}")
        image_path = scrape_channel(SOURCE_CHANNEL_1, base_start_time, current_time)
        if image_path:
            print(f"[INFO] تصویر مورد نظر در تلاش {attempt} پیدا شد.")
            break
        if current_time >= stop_time:
            print("[INFO] زمان اجرای کد به ساعت 03:02 رسیده است. پایان تلاش‌ها.")
            break
        print(f"[INFO] در تلاش {attempt} تصویر پیدا نشد. 5 دقیقه صبر می‌کنیم.")
        await asyncio.sleep(5 * 60)

    if image_path:
        cropped_image_path = crop_image(image_path, CROP_HEIGHT)
        await send_photo(cropped_image_path)
    else:
        print("[INFO] پس از پایان دوره (تا 03:02)، تصویر مورد نظر پیدا نشد.")

if __name__ == '__main__':
    asyncio.run(main())
