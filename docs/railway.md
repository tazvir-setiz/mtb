# راهنمای جامع استقرار و راه‌اندازی سرور (Deployment & Hosting)

این راهنما آموزش کامل نحوه استقرار ربات **MTB Telegram Forwarder** را بر روی سرویس‌های ابری نظیر **Railway**، سرورهای مجازی شخصی (**VPS Linux**) و کانتینرهای **Docker** ارائه می‌دهد.

ربات یک سرویس دائمی (Long-running Background Daemon) است و نیازی به دامنه اختصاصی، وب‌سرور، وب‌هوک (Webhook) یا باز کردن پورت اینترنتی ندارد.

---

## ۱. پیش‌نیازها و اطلاعات هویتی مورد نیاز

| متغیر محیطی | توضیح | روش دریافت |
|---|---|---|
| `BOT_TOKEN` | توکن ربات تلگرامی مدیریت | ارسال `/newbot` به ربات رسمی [@BotFather](https://t.me/BotFather) |
| `API_ID` و `API_HASH` | کلیدهای اتصال کلاینت Telethon | ثبت‌نام و ساخت App در سایت رسمی [my.telegram.org](https://my.telegram.org) |
| `ADMIN_IDS` | شناسه‌های عددی ادمین‌های ربات | شناسه عددی اکانت خود را از ربات‌هایی مثل [@userinfobot](https://t.me/userinfobot) بگیرید |
| اکانت تلگرام | شماره تلفنی که عضو کانال‌هاست | این اکانت باید عضو کانال‌های مبدأ و ادمین کانال‌های مقصد باشد |

> [!IMPORTANT]
> ربات مدیریتی (`BOT_TOKEN`) و اکانت کاربری Telethon دو هویت کاملاً مجزا هستند. دسترسی خواندن از کانال‌های خصوصی مبدأ و اجازه انتشار در کانال‌های مقصد متعلق به **اکانت کاربری Telethon** است.

---

## ۲. آماده‌سازی و استخراج رشته سشن (Session Generation)

از آنجا که سرورهای ابری نظیر Railway کنسول تعاملی برای وارد کردن کد پیامک ورود ندارند، ابتدا باید ورود را یک‌بار روی کامپیوتر خود انجام داده و رشته نشست (`TELETHON_STRING_SESSION`) را استخراج کنید:

1. در خط فرمان یا PowerShell به پوشه پروژه بروید.
2. اسکریپت استخراج سشن را اجرا کنید:
   ```powershell
   python -m scripts.export_session
   ```
3. شماره تلفن بین‌المللی اکانت (مثلاً `+989123456789`) را وارد کنید.
4. کد تأیید ارسال‌شده در تلگرام و رمز عبور دومرحله‌ای (در صورت داشتن 2FA) را وارد نمایید.
5. پس از ورود موفق، رشته نشست طولانی در فایل `sessions/railway-session.txt` ذخیره می‌شود.

> [!CAUTION]
> این رشته نشست مجوز ورود به حساب کاربری تلگرام شماست! هرگز آن را در گیت‌هاب کامیت نکنید یا در گروه‌ها نفرستید.

---

## ۳. استقرار روی سرویس ابری Railway

1. پروژه خود را در گیت‌هاب (به صورت مخزن خصوصی یا عمومی) Push کنید.
2. در داشبورد [Railway.app](https://railway.app)، یک **New Project** بسازید و گزینه **Deploy from GitHub repo** را انتخاب کنید.
3. در تنظیمات سرویس (Settings)، بررسی کنید که بخش Build از **Dockerfile** استفاده کند.
4. **ایجاد حجم دائمی (Persistent Volume):**
   - وارد تب **Volume** سرویس شوید و دکمه **Add Volume** را بزنید.
   - مقدار Mount Path را دقیقاً `/data` قرار دهید. این کار باعث می‌شود دیتابیس و فایل‌های سشن با هر بار راه‌اندازی سرور حفظ شوند.
5. **تنظیم متغیرهای محیطی (Variables):**
   در تب **Variables** مقادیر زیر را وارد کنید:
   ```dotenv
   BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ
   API_ID=12345678
   API_HASH=0123456789abcdef0123456789abcdef
   ADMIN_IDS=123456789
   DATABASE_URL=sqlite:////data/forwarder.db
   TELETHON_SESSION=/data/forwarder_session
   TELETHON_STRING_SESSION=متن_کپی_شده_از_railway-session.txt
   AI_ENABLED=true
   AI_API_KEY=کلید_سرویس_هوش_مصنوعی_شما
   AI_MODEL=google/gemini-2.5-flash
   AI_BASE_URL=https://openrouter.ai/api/v1
   LOG_LEVEL=INFO
   ```
6. سرویس به صورت خودکار بیلد و اجرا می‌شود. اکنون می‌توانید در تلگرام دستور `/start` را برای ربات خود ارسال کنید.

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
nano .env  # اطلاعات توکن و دیتابیس را وارد کنید
```

### ۲. ساخت سرویس سیستمی (Systemd Service) برای اجرای دائمی:
یک فایل سرویس ایجاد کنید:
```bash
sudo nano /etc/systemd/system/telegram-forwarder.service
```

محتوای زیر را داخل آن قرار دهید:
```ini
[Unit]
Description=MTB Telegram Forwarder Bot
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
