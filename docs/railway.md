# راهنمای جامع استقرار و راه‌اندازی سرور (Deployment & Hosting)

این راهنما آموزش کامل نحوه استقرار ربات **MTB Forwarder** (پشتیبانی از تلگرام و پیام‌رسان بله) را بر روی سرویس‌های ابری نظیر **Railway**، سرورهای مجازی شخصی (**VPS Linux**) و کانتینرهای **Docker** ارائه می‌دهد.

ربات یک سرویس دائمی (Long-running Background Daemon) مبتنی بر Long Polling است و نیازی به دامنه اختصاصی، وب‌سرور، وب‌هوک (Webhook) یا باز کردن پورت اینترنتی ندارد.

---

## ۱. پیش‌نیازها و اطلاعات هویتی مورد نیاز

| متغیر محیطی | توضیح | روش دریافت |
|---|---|---|
| `PLATFORM` | پلتفرم هدف (`telegram` یا `bale`) | پیش‌فرض `telegram` است؛ برای بله مقدار را `bale` بگذارید |
| `BOT_TOKEN` | توکن رسمی ربات (تلگرام یا بله) | **تلگرام:** ربات [@BotFather](https://t.me/BotFather)<br>**بله:** بازوی [@BotFather](https://ble.ir/botfather) |
| `ADMIN_IDS` | شناسه‌های عددی ادمین‌های ربات | شناسه عددی اکانت خود را از ربات‌هایی مثل [@userinfobot](https://t.me/userinfobot) بگیرید |
| `DATABASE_URL` | آدرس اتصال به پایگاه داده | `sqlite:////data/forwarder.db` یا PostgreSQL |
| `API_ID` و `API_HASH` | *(اختیاری / موروثی)* کلیدهای کلاینت Telethon | در معماری جدید ربات نیازی به این متغیرها نیست |
| `TELETHON_STRING_SESSION` | *(اختیاری / موروثی)* نشست کاربری Telethon | در معماری جدید نیازی به ورود تلفنی و سشن کاربری نیست |

> [!IMPORTANT]
> **معماری ربات‌محور (Bot-Native):**  
> سیستم اکنون تمام عملیات دریافت پست‌های کانال و ارسال به کانال‌های مقصد را مستقیماً از طریق **Bot API** تلگرام یا بله انجام می‌دهد. دیگر نیازی به سیم‌کارت، لاگین با شماره تلفن و کدهای یکبارمصرف پیامکی نیست. کافی است ربات را به عنوان ادمین (با دسترسی ارسال پیام) در کانال‌های مقصد و مبدأ عضو کنید.

---

## ۲. راه‌اندازی و شناسایی در تلگرام و بله

### الف) اتصال به تلگرام (Telegram)
1. در تلگرام به [@BotFather](https://t.me/BotFather) پیام دهید و دستور `/newbot` را بزنید تا ربات ساخته شده و `BOT_TOKEN` به شما داده شود.
2. در تنظیمات ربات در BotFather، در صورت تمایل حریم خصوصی گروه را مدیریت کنید.
3. در متغیرهای محیطی `PLATFORM=telegram` قرار دهید.

### ب) اتصال به پیام‌رسان بله (Bale)
1. در پیام‌رسان بله به بازوی رسمی [@BotFather](https://ble.ir/botfather) مراجعه کرده و یک ربات جدید ایجاد کنید.
2. توکن اختصاصی صادرشده را دریافت نمایید.
3. در متغیرهای محیطی `PLATFORM=bale` قرار دهید. سیستم به طور خودکار `BOT_BASE_URL=https://tapi.bale.ai/bot` را به کار خواهد گرفت.

> [!NOTE]
> **پشتیبانی از سشن کاربری قدیمی (Legacy Telethon):**  
> چنانچه بخواهید از قابلیت‌های قدیمی خواندن از کانال‌های خصوصی بدون عضویت ربات استفاده کنید، می‌توانید اسکریپت `python -m scripts.export_session` را اجرا کنید و رشته سشن را در `TELETHON_STRING_SESSION` قرار دهید؛ اما برای عملکرد عادی سیستم هیچ نیازی به این مرحله نیست.

---

## ۳. استقرار روی سرویس ابری Railway

1. پروژه خود را در گیت‌هاب (به صورت مخزن خصوصی یا عمومی) Push کنید.
2. در داشبورد [Railway.app](https://railway.app)، یک **New Project** بسازید و گزینه **Deploy from GitHub repo** را انتخاب کنید.
3. در تنظیمات سرویس (Settings)، بررسی کنید که بخش Build از **Dockerfile** استفاده کند.
4. **ایجاد حجم دائمی (Persistent Volume):**
   - وارد تب **Volume** سرویس شوید و دکمه **Add Volume** را بزنید.
   - مقدار Mount Path را دقیقاً `/data` قرار دهید. این کار باعث می‌شود دیتابیس با هر بار راه‌اندازی سرور حفظ شود.
5. **تنظیم متغیرهای محیطی (Variables):**
   در تب **Variables** مقادیر زیر را وارد کنید:
   ```dotenv
   PLATFORM=telegram
   BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ
   ADMIN_IDS=123456789
   DATABASE_URL=sqlite:////data/forwarder.db
   AI_ENABLED=true
   AI_API_KEY=کلید_سرویس_هوش_مصنوعی_شما
   AI_MODEL=google/gemini-2.5-flash
   AI_BASE_URL=https://openrouter.ai/api/v1
   LOG_LEVEL=INFO
   ```
6. سرویس به صورت خودکار بیلد و اجرا می‌شود. اکنون می‌توانید در پیام‌رسان دستور `/start` را برای ربات خود ارسال کنید.

---

## ۴. استقرار روی سرور لینوکس شخصی (Ubuntu / Debian VPS)

اگر مایلید ربات را روی سرور مجازی اختصاصی خود اجرا کنید:

### ۱. نصب پیش‌نیازها و پایتون:
```bash
sudo apt update && sudo apt install -y python3 python3-venv git
git clone https://github.com/your-username/telegram-forwarder.git
cd telegram-forwarder
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env  # اطلاعات توکن، پلتفرم و دیتابیس را وارد کنید
```

### ۲. ساخت سرویس سیستمی (Systemd Service) برای اجرای دائمی:
یک فایل سرویس ایجاد کنید:
```bash
sudo nano /etc/systemd/system/telegram-forwarder.service
```

محتوای زیر را داخل آن قرار دهید:
```ini
[Unit]
Description=MTB Forwarder Bot (Telegram & Bale)
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/telegram-forwarder
ExecStart=/root/telegram-forwarder/.venv/bin/python main.py
Restart=always
RestartSec=5
EnvironmentFile=/root/telegram-forwarder/.env

[Install]
WantedBy=multi-user.target
```

فعال‌سازی و شروع سرویس:
```bash
sudo systemctl daemon-reload
sudo systemctl enable telegram-forwarder
sudo systemctl start telegram-forwarder
sudo systemctl status telegram-forwarder
```

برای مشاهده لاگ‌های زنده سرویس در سرور:
```bash
journalctl -u telegram-forwarder -f
```
ExecStart=/root/telegram-forwarder/.venv/bin/python main.py
Restart=always
RestartSec=5
EnvironmentFile=/root/telegram-forwarder/.env

[Install]
WantedBy=multi-user.target
```

فعال‌سازی و شروع سرویس:
```bash
sudo systemctl daemon-reload
sudo systemctl enable telegram-forwarder
sudo systemctl start telegram-forwarder
sudo systemctl status telegram-forwarder
```

برای مشاهده لاگ‌های زنده سرویس در سرور:
```bash
journalctl -u telegram-forwarder -f
```
