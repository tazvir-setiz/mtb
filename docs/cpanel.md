# راه‌اندازی مرحله‌به‌مرحله روی cPanel

این پروژه یک پردازش دائمی Python است: هم فرمان‌های ربات را با polling دریافت می‌کند و هم به حساب تلگرام با Telethon متصل می‌شود. سایت WSGI نیست؛ قرار دادن `main.py` در Passenger یا باز کردن آدرس سایت، روش اجرای آن نیست. دامنه و SSL برای خود ربات لازم نیست.

در تمام نمونه‌ها `CPANEL_USER` را با نام واقعی کاربر هاست و مسیر `/home/CPANEL_USER` را با Home واقعی حساب جایگزین کنید. دستورات Bash در Terminal یا SSH سرور اجرا می‌شوند، مگر جایی که PowerShell نوشته شده است.

## ۱. ابتدا سازگاری هاست را بررسی کنید

این پرسش را برای پشتیبانی هاست بفرستید:

> برای یک Telegram worker به Python 3.12، venv و pip، دسترسی Terminal/SSH، اتصال خروجی به Telegram Bot API و MTProto و سرویس AI، و اجازه اجرای دائمی پردازش پس‌زمینه نیاز دارم. آیا پلن من اجازه این کار را دارد؟ آیا process manager در اختیارم می‌گذارید، یا اجرای دائمی با Cron و flock مجاز است؟ محدودیت زمان اجرای پردازش، حافظه و Cron چیست؟

داشتن «Setup Python App» به‌تنهایی کافی نیست. Application Manager مبتنی بر Passenger برای برنامه‌های وب است؛ نیاز این پروژه را از روی آن نمی‌توان نتیجه گرفت. [مستندات Application Manager](https://docs.cpanel.net/cpanel/software/application-manager/)

| وضعیت هاست | مسیر اجرا |
|---|---|
| VPS دارای cPanel و دسترسی مدیریتی | مراحل مشترک و سپس روش A با systemd |
| هاست اشتراکی با اجازه صریح اجرای دائمی، SSH و flock | مراحل مشترک و روش B؛ محدودیت میزبان همچنان برقرار است |
| هاست فقط وب یا دارای ممنوعیت پردازش دائمی | اجرای پایدار این پروژه روی آن ممکن نیست؛ پلن مناسب، VPS یا Railway لازم است |

روش A و B را هم‌زمان فعال نکنید. اجرای این ربات روی Railway یا کامپیوتر نیز باید هنگام شروع نسخه cPanel متوقف باشد.

## ۲. آماده‌سازی اعتبارنامه و نشست روی کامپیوتر

۱. توکن ربات را از `@BotFather` با `/newbot` بگیرید.
۲. `API_ID` و `API_HASH` را از `my.telegram.org` بخش API development tools بگیرید.
۳. شناسه **عددی حساب مدیر** را آماده کنید؛ نه نام کاربری، شماره تلفن یا آیدی کانال. چند مدیر با کاما جدا می‌شوند.
۴. حسابی که وارد Telethon می‌شود باید به مبدأ دسترسی و در مقصد اجازه انتشار داشته باشد. ربات مدیریتی و این حساب دو هویت جدا هستند.

منابع: [ساخت ربات](https://core.telegram.org/bots/tutorial)، [ساخت برنامه تلگرام](https://core.telegram.org/api/obtaining_api_id).

در کامپیوتر ویندوز، اجرای محلی ربات را متوقف کنید و در PowerShell به پروژه بروید:

```powershell
cd "D:\Habib\mtb\New folder\telegram-forwarder"
```

اگر محیط مجازی ندارید با Python 3.12 بسازید؛ برای محیط موجود فقط نصب وابستگی‌ها لازم است:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

اگر `.env` ندارید از `.env.example` کپی بسازید؛ فایل موجود را بازنویسی نکنید. اعتبارنامه‌ها را داخل آن تنظیم کنید. برای مسیر محلی از `TELETHON_SESSION=sessions/forwarder_session` استفاده کنید. اگر اتصال مستقیم تلگرام برقرار است `PROXY_ENABLED=false` بگذارید؛ در غیر این صورت پروکسی فعال محلی را تنظیم کنید.

```powershell
.\.venv\Scripts\python.exe -m scripts.export_session
```

در صورت درخواست، شماره، کد ورود و رمز دومرحله‌ای را وارد کنید. خروجی `sessions/railway-session.txt` است؛ با وجود نام آن، روی cPanel نیز قابل استفاده است. اسکریپت فایل موجود را بازنویسی نمی‌کند؛ خروجی قبلی معتبر را استفاده یا قبل از صدور تازه به محل خصوصی پشتیبان منتقل کنید.

این فایل مجوز ورود حساب است؛ آن را در مخزن، چت یا فضای عمومی قرار ندهید. اگر Timeout گرفتید، اول شبکه و پروکسی کامپیوتر را اصلاح کنید.

## ۳. انتقال کد به پوشه خصوصی هاست

۱. در File Manager، داخل Home حساب و **بیرون `public_html`** پوشه `telegram-forwarder` بسازید.
۲. نسخه موردنظر کد را منتقل کنید. برای ساخت ZIP از فایل‌های commit‌شده، روی کامپیوتر اجرا کنید:

```powershell
git archive --format=zip -o telegram-forwarder-deploy.zip HEAD
```

این دستور فقط آخرین commit را بسته‌بندی می‌کند؛ تغییرات commit‌نشده داخل ZIP نیستند. پیش از آپلود مطمئن شوید مخزن فایل محرمانه tracked ندارد. کل پوشه کار، `.venv` ویندوز، دیتابیس و نشست‌ها را ZIP نکنید.
۳. ZIP را در پوشه خصوصی ساخته‌شده آپلود و Extract کنید. ساختار باید این‌گونه باشد؛ پوشه تودرتوی اضافی نسازید:

```text
/home/CPANEL_USER/telegram-forwarder/
    main.py
    requirements.txt
    app/
    scripts/
```

۴. در Terminal یا SSH وارد همان پوشه شوید:

```bash
cd /home/CPANEL_USER/telegram-forwarder
pwd
python3.12 --version
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
mkdir -p data sessions logs run
chmod 700 data sessions logs run
```

اگر دستور `python3.12` یا ماژول venv موجود نیست، مسیر Python سازگار یا فعال‌سازی آن را از پشتیبانی بگیرید؛ Python سیستم را با دسترسی root جایگزین نکنید. مسیر Python ارائه‌شده را در دستور ساخت venv استفاده کنید. محیط مجازی ویندوز روی لینوکس قابل استفاده نیست.

## ۴. فایل تنظیمات سرور

در File Manager نمایش فایل‌های مخفی را فعال و در ریشه پروژه فایل `.env` بسازید. برای نصب تازه نمونه زیر را وارد کنید و همه مقادیر نمونه و `CPANEL_USER` را عوض کنید. روی نصب موجود، فایل تنظیمات را جایگزین نکنید.

```dotenv
BOT_TOKEN=REPLACE_WITH_BOT_TOKEN
API_ID=123456
API_HASH=REPLACE_WITH_API_HASH
ADMIN_IDS=123456789
TELETHON_STRING_SESSION=REPLACE_WITH_SESSION_FILE_CONTENT
DATABASE_URL=sqlite:////home/CPANEL_USER/telegram-forwarder/data/forwarder.db
TELETHON_SESSION=/home/CPANEL_USER/telegram-forwarder/sessions/forwarder_session
PROXY_ENABLED=false
LOG_LEVEL=INFO
LOG_TO_FILE=true
FORWARD_DELAY=1.5
PROGRESS_UPDATE_INTERVAL=3
AI_ENABLED=false
AI_GUARD_MAX_OUTPUT_TOKENS=1024
AI_GUARD_TIMEOUT_SECONDS=60
AI_GUARD_TOTAL_TIMEOUT_SECONDS=120
AI_GUARD_MAX_STAGES=6
AI_GUARD_MAX_REQUESTS=8
```

محتوای کامل فایل نشست را بدون کوتیشن اضافه قرار دهید. URL دیتابیس بعد از `sqlite:` چهار اسلش دارد. به مسیر نشست پسوند اضافه نکنید. پروکسی localhost کامپیوتر، روی هاست کار نمی‌کند. این پروژه `.env` را خودش می‌خواند؛ اجرای `source .env` لازم نیست.

```bash
chmod 600 .env
```

جدول‌های دیتابیس در اولین اجرا ساخته می‌شوند. `AI_ENABLED=false` یعنی پالایش AI خاموش است؛ تا تنظیم AI، انتقال خودکار را روشن نکنید.

## ۵. آزمایش تعاملی

ابتدا همه اجراهای دیگر با همین توکن و نشست را متوقف کنید. سپس:

```bash
cd /home/CPANEL_USER/telegram-forwarder
.venv/bin/python -u main.py
```

۱. نباید درخواست ورود تعاملی تلگرام داشته باشید؛ نشست از مرحله ۲ تأمین شده است.
۲. از حساب مدیر در چت خصوصی ربات `/start` بفرستید.
۳. اتصال را در لاگ بررسی کنید؛ گزارش دوره‌ای باید `telegram_connected=True` داشته باشد.
۴. با `Ctrl+C` برنامه را متوقف کنید و تا برگشت prompt منتظر بمانید.

باز گذاشتن Terminal روش اجرای دائمی نیست. پس از موفقیت، **یکی** از دو روش زیر را انتخاب کنید.

## ۶. روش A: systemd روی VPS دارای دسترسی مدیریتی

این بخش را مدیر سرور دارای root/sudo انجام می‌دهد؛ روی هاست اشتراکی معمولاً در دسترس نیست. برنامه با کاربر cPanel اجرا می‌شود، نه root. فایل‌های پروژه و پوشه‌های داده باید برای همان کاربر قابل خواندن/نوشتن باشند.

مدیر سرور فایل `/etc/systemd/system/telegram-forwarder.service` را بسازد:

```ini
[Unit]
Description=Telegram Forwarder
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=CPANEL_USER
WorkingDirectory=/home/CPANEL_USER/telegram-forwarder
ExecStart=/home/CPANEL_USER/telegram-forwarder/.venv/bin/python -u /home/CPANEL_USER/telegram-forwarder/main.py
Environment=PYTHONUNBUFFERED=1
UMask=0077
Restart=on-failure
RestartSec=10
TimeoutStopSec=150

[Install]
WantedBy=multi-user.target
```

پس از جایگزینی نام کاربر و مسیرها، مدیر سرور اجرا کند:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now telegram-forwarder
sudo systemctl status telegram-forwarder --no-pager
sudo journalctl -u telegram-forwarder -n 100 --no-pager
```

وضعیت مورد انتظار `active (running)` است؛ پاسخ `/start` و لاگ اتصال را هم بررسی کنید. برای توقف و شروع:

```bash
sudo systemctl stop telegram-forwarder
sudo systemctl start telegram-forwarder
```

برای این روش Cron نسازید. systemd شروع پس از reboot و بازیابی از خروج خطادار را مدیریت می‌کند.

## ۷. روش B: هاست اشتراکی مجاز با Cron و flock

فقط وقتی پشتیبانی اجازه اجرای دائمی می‌دهد از این روش استفاده کنید. Cron محدودیت میزبان یا قطع اجباری پردازش را برطرف نمی‌کند. اگر میزبان process manager رسمی دارد، همان را برای اجرای `.venv/bin/python -u main.py` با Working Directory پروژه تنظیم کنید.

ابتدا مسیر و قابلیت flock را بررسی کنید:

```bash
command -v flock
flock --help
```

دستور زیر به گزینه‌های `-n` و `-F` نیاز دارد. نمونه فرض می‌کند مسیر flock برابر `/usr/bin/flock` است؛ اگر خروجی متفاوت بود همان را استفاده کنید. `-n` جلوی اجرای موازی را می‌گیرد و `-F` پردازش اضافه ایجاد نمی‌کند. [راهنمای flock](https://man7.org/linux/man-pages/man1/flock.1.html)

در پوشه پروژه فایل `run-bot.sh` را با پایان خط **LF** و محتوای زیر بسازید:

```bash
#!/bin/bash
set -eu
umask 077
cd /home/CPANEL_USER/telegram-forwarder
printf '%s\n' "$$" > run/bot.pid
exec .venv/bin/python -u main.py
```

```bash
chmod 700 run-bot.sh
```

در cPanel بخش **Cron Jobs** یک کار بسازید. اگر میزبان اجرای هر دقیقه را مجاز می‌داند، پنج فیلد زمان را `*` قرار دهید؛ وگرنه حداقل فاصله مجاز میزبان را انتخاب کنید. در فیلد Command فقط این دستور را قرار دهید؛ پنج ستاره را آنجا ننویسید:

```bash
/usr/bin/flock -n -F /home/CPANEL_USER/telegram-forwarder/run/bot.lock /bin/bash /home/CPANEL_USER/telegram-forwarder/run-bot.sh >> /home/CPANEL_USER/telegram-forwarder/logs/launcher.log 2>&1
```

Cron هر بار فقط تلاش می‌کند worker را در صورت نبود اجرای قبلی شروع کند؛ دریافت پیام توسط همان پردازش دائمی انجام می‌شود، نه یک اجرای کوتاه در هر دقیقه. نام lock و این مسیر را برای همه شروع‌های این روش ثابت نگه دارید. فایل lock را در زمان اجرا حذف نکنید. [راهنمای Cron در cPanel](https://docs.cpanel.net/cpanel/advanced/cron-jobs/)

تا نوبت Cron منتظر بمانید و سپس بررسی کنید:

```bash
tail -n 80 logs/launcher.log
cat run/bot.pid
```

`logs/launcher.log` با این redirect چرخش خودکار ندارد؛ با پشتیبانی برای log rotation تنظیم کنید و حجم آن را پایش کنید. لاگ‌های داخلی `app.log` و `error.log` چرخشی هستند.

### توقف امن روش B

۱. ابتدا Cron مربوط به ربات را غیرفعال یا حذف کنید تا دوباره شروع نشود.
۲. PID را از `run/bot.pid` بخوانید.
۳. به‌جای `12345` مقدار واقعی را بگذارید و هویت پردازش را بررسی کنید:

```bash
ps -p 12345 -o pid=,args=
```

۴. فقط اگر همان Python و `main.py` این پروژه است، متوقف کنید:

```bash
kill -TERM 12345
```

۵. تا پایان پردازش صبر کنید و دوباره `ps` را بررسی کنید. PID قدیمی ممکن است متعلق به برنامه دیگری شده باشد؛ بدون بررسی kill نکنید. از `pkill python` استفاده نکنید. برای شروع دوباره Cron را برگردانید.

## ۸. تنظیم ربات پس از اجرای دائمی

۱. مبدأ و مقصد را در داشبورد تنظیم کنید؛ مقصد آزمایشی انتخاب کنید.
۲. در تنظیمات AI، ابتدا آدرس کامل سرویس Chat Completions را ثبت کنید. تغییر آدرس، کلید قبلی را پاک و AI را خاموش می‌کند.
۳. کلید API و مدل معتبر سرویس‌دهنده را وارد و AI را فعال کنید. آدرس نمونه: `https://api.openai.com/v1/chat/completions`؛ قالب Markdown ننویسید.
۴. امضا و رفتار لینک‌ها/آیدی‌ها را تعیین کنید.
۵. یک پیام عادی و یک پیام نیازمند بازنویسی را آزمایش کنید و متن خروجی و لاگ را ببینید.
۶. Auto-Forward را روشن و یک پیام جدید در مبدأ ایجاد کنید. برای آرشیو از انتقال دستی استفاده کنید.
۷. `/reviews` را ببینید و در صورت نیاز رد، تأیید یا ویرایش کنید؛ تأیید دستی ممکن است انتشار واقعی انجام دهد.

تنظیم AI ذخیره‌شده در دیتابیس بر پیش‌فرض env اولویت دارد؛ برای تغییر بعدی از منوی ربات استفاده کنید. خالی بودن `AI_GUARDRAILS` یعنی قوانین همراه پروژه. سقف ۶ مرحله/۸ درخواست، تعداد اجباری فراخوانی هر پیام نیست.

## ۹. لاگ و تشخیص سلامت

```bash
cd /home/CPANEL_USER/telegram-forwarder
tail -n 100 logs/app.log
tail -n 100 logs/error.log
```

گزارش دوره‌ای را بررسی کنید: اتصال تلگرام، فعال بودن انتقال خودکار، تعداد دریافت/ارسال، صف و خطاهای AI. روشن بودن پردازش به‌تنهایی تضمین انتشار نیست؛ DROP، Review، پیام تکراری و متن خالی را از خطای ارتباط تفکیک کنید. فایل‌های لاگ را عمومی نکنید و هنگام ارسال برای پشتیبانی، اطلاعات حساس را حذف کنید.

## ۱۰. پشتیبان و آپدیت

۱. با روش منتخب، worker را متوقف کنید؛ در روش B اول Cron را غیرفعال کنید.
۲. پایان پردازش را بررسی کنید تا دیتابیس در حال نوشتن نباشد.
۳. از داده، نشست و تنظیمات در Home خصوصی پشتیبان بگیرید:

```bash
cd /home/CPANEL_USER/telegram-forwarder
umask 077
mkdir -p /home/CPANEL_USER/forwarder-backups
tar -czf "/home/CPANEL_USER/forwarder-backups/forwarder-$(date +%Y%m%d-%H%M%S).tar.gz" .env data sessions
```

این آرشیو حاوی کلید و نشست است؛ خارج از `public_html` و خصوصی نگه دارید. از فایل SQLite در حال نوشتن، به‌تنهایی کپی نگیرید.
۴. کد نسخه جدید را جایگزین کنید؛ `.env`، `data`، `sessions`، `logs`، `run` و محیط مجازی سرور را نگه دارید. ابتدا نسخه فعلی کد/شماره commit را برای برگشت ثبت کنید.
۵. وابستگی‌ها را به‌روز کنید:

```bash
.venv/bin/python -m pip install -r requirements.txt
```

۶. با همان روش منتخب worker را شروع و پاسخ `/start`، کانال‌ها، تنظیمات و لاگ را بررسی کنید.

برای بازیابی، worker را متوقف و آرشیو انتخاب‌شده را ابتدا در پوشه خصوصی جدا استخراج کنید؛ پس از بررسی، فایل‌های تنظیمات، داده و نشست را به مسیرهای درست برگردانید. برگشت کد و برگشت دیتابیس دو کار جدا هستند. نصب تازه خودکار داده‌های Railway یا کامپیوتر را دریافت نمی‌کند.

## ۱۱. خطاهای رایج

| نشانه | اقدام |
|---|---|
| `python3.12: command not found` یا نبود venv | مسیر/نصب Python مناسب را از پشتیبانی بگیرید |
| `Permission denied` یا دیتابیس readonly | مالکیت و دسترسی مسیرهای خصوصی برای کاربر اجرا را اصلاح کنید؛ `chmod 777` نزنید |
| `interactive login is unavailable` | نشست معتبر محلی را در `.env` قرار دهید |
| تغییر رشته نشست اثری ندارد | فایل نشست موجود مرجع است. worker را متوقف و پشتیبان بگیرید؛ فقط نشست قبلی و فایل‌های جانبی همان نشست را کنار بگذارید تا از رشته تازه ساخته شود؛ دیتابیس برنامه را نگه دارید |
| `Conflict ... getUpdates` | اجرای Railway/محلی/اضافی با همین توکن را متوقف کنید |
| `database is locked` | اجرای موازی یا استفاده هم‌زمان از نشست را بررسی کنید |
| بعد از بستن Terminal متوقف می‌شود | روش اجرای دائمی را کامل کنید؛ اجرای تعاملی کافی نیست |
| Cron اجرا نمی‌شود | مسیرهای مطلق، مجوز میزبان، وجود flock و `launcher.log` را بررسی کنید |
| `bad interpreter` یا خطای `\r` | فایل shell را با پایان خط LF ذخیره کنید |
| مرتب کشته می‌شود یا حافظه کم می‌آورد | محدودیت پردازش/حافظه هاست را با پشتیبانی بررسی کنید؛ Cron تضمین پایداری نیست |
| timeout تلگرام | دسترسی خروجی MTProto و Bot API و تنظیم پروکسی سرور را بررسی کنید |
| timeout یا خطای AI | آدرس/کلید/مدل داخل ربات و لاگ مرحله را بررسی کنید؛ بودجه زمان تضمین پاسخ سرویس نیست |
| مبدأ یا مقصد در دسترس نیست | مجوزهای حساب کاربری Telethon را بررسی کنید؛ صرف ادمین بودن ربات کافی نیست |
