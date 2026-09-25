# Telegram Forwarder Bot

ربات مدیریتی برای **Forward واقعی پیام‌ها** از یک کانال مبدأ به یک کانال مقصد،
با رابط کاربری کاملاً Inline (بدون نیاز به Command)، مدیریت FloodWait، جلوگیری
از پیام‌های تکراری، Progress زنده، Retry و ذخیره کامل وضعیت در SQLite.

---

## فهرست مطالب

1. [معرفی پروژه](#۱-معرفی-پروژه)
2. [معماری](#۲-معماری)
3. [محدودیت‌های واقعی Telegram](#۳-محدودیتهای-واقعی-telegram)
4. [نصب Python](#۴-نصب-python)
5. [ساخت Virtual Environment](#۵-ساخت-virtual-environment)
6. [نصب Dependencies](#۶-نصب-dependencies)
7. [ساخت Bot در BotFather](#۷-ساخت-bot-در-botfather)
8. [گرفتن Bot Token](#۸-گرفتن-bot-token)
9. [گرفتن API ID و API Hash](#۹-گرفتن-api-id-و-api-hash)
10. [تنظیم .env](#۱۰-تنظیم-env)
11. [اضافه کردن ربات به کانال‌ها](#۱۱-اضافه-کردن-ربات-به-کانالها)
12. [تنظیم Administrator Permissions](#۱۲-تنظیم-administrator-permissions)
13. [اجرای پروژه](#۱۳-اجرای-پروژه)
14. [اولین Login به Telethon](#۱۴-اولین-login-به-telethon)
15. [استفاده از Dashboard](#۱۵-استفاده-از-dashboard)
16. [Forward کردن اولین پیام](#۱۶-forward-کردن-اولین-پیام)
17. [مدیریت FloodWait](#۱۷-مدیریت-floodwait)
18. [خطاهای رایج](#۱۸-خطاهای-رایج)
19. [Backup Database و Session](#۱۹-backup-database-و-session)
20. [اجرای Production](#۲۰-اجرای-production)
21. [تست‌ها](#۲۱-تستها)
22. [ویندوز (PowerShell)](#۲۲-ویندوز-powershell)

---

## ۱. معرفی پروژه

این پروژه یک ربات تلگرام است که با یک پنل کاملاً گرافیکی (Inline Keyboard)
اجازه می‌دهد پیام‌های یک کانال (مبدأ) — با بازه Message ID دلخواه یا لیست
مشخص — به‌صورت **Forward واقعی** (نه کپی متن) به کانال دیگری (مقصد) منتقل
شوند. تمام وضعیت عملیات، پیام‌های موفق/ناموفق/تکراری و آمار در SQLite ذخیره
می‌شود و در صورت قطع شدن برنامه، عملیات نیمه‌کاره قابل ادامه است.

## ۲. معماری

پروژه از **دو مکانیزم مکمل** استفاده می‌کند:

| بخش | تکنولوژی | دلیل |
|---|---|---|
| پنل مدیریت (Dashboard, دکمه‌ها، پیام‌ها) | **python-telegram-bot** (Bot API) | ساده، پایدار و مخصوص UI ادمین |
| خواندن تاریخچه کانال و Forward واقعی | **Telethon** (MTProto Client API) | Bot API این قابلیت را ندارد (بند ۳) |

یعنی UI ادمین را با `BOT_TOKEN` اداره می‌کنید، اما عملیات واقعی خواندن و
Forward کردن پیام‌های کانال، توسط یک **حساب کاربری واقعی تلگرام** (متصل با
`API_ID`/`API_HASH` از طریق Telethon) انجام می‌شود. این حساب باید عضو کانال
مبدأ و ادمین کانال مقصد باشد.

معماری Modular است:

```text
telegram-forwarder/
├── app/
│   ├── config.py            # بارگذاری .env
│   ├── logging_config.py    # تنظیم لاگ کنسول و فایل‌های چرخشی
│   ├── database/            # مدل‌ها و اتصال SQLAlchemy
│   │   └── repositories/    # channels.py / jobs.py / messages.py / settings.py
│   ├── telegram/            # اتصال، راه‌اندازی ربات و هماهنگی انتقال‌ها
│   │   ├── message_sender.py # پردازش و ارسال مشترک انتقال دستی و خودکار
│   │   ├── forward_errors.py # دسته‌بندی خطاها و متن قابل نمایش
│   │   └── forward_progress.py # ساختار داده پیشرفت انتقال
│   ├── handlers/            # auth.py / commands.py / router.py و هندلرهای صفحات
│   │   └── callback_routes.py # جدول اتصال دکمه‌ها به هندلرها
│   ├── ui/                  # مسیرهای عمومی messages.py / keyboards.py / callbacks.py
│   │   ├── texts/           # متن‌ها به تفکیک صفحه
│   │   └── buttons/         # دکمه‌ها به تفکیک صفحه
│   ├── services/            # انتقال، ثبت نتیجه، پیشرفت، آمار و AI
│   └── utils/                # validators.py, helpers.py
├── data/                    # فایل SQLite
├── sessions/                # فایل Session تلتون (حساس - Commit نشود)
├── logs/                    # app.log / error.log
├── tests/                   # Unit Testها (Mock شده، بدون نیاز به تلگرام واقعی)
├── main.py
└── requirements.txt
```

Handlerها فقط event دریافت می‌کنند و Service مربوطه را صدا می‌زنند؛ منطق
Forward و دسترسی به Telegram API هرگز داخل Handler نیست.

برای پیدا کردن محل تغییر یا دیباگ:

| موضوع | محل اصلی |
|---|---|
| دکمه‌ای که به صفحه اشتباه می‌رود | `app/handlers/callback_routes.py` |
| دسترسی ادمین و ورودی متنی | `app/handlers/auth.py` و `router.py` |
| متن یا ظاهر یک صفحه | فایل هم‌نام صفحه در `app/ui/texts/` و `app/ui/buttons/` |
| پردازش AI، امضا، رسانه و ارسال پیام | `app/telegram/message_sender.py` |
| حلقه انتقال، توقف و تلاش مجدد پس از FloodWait | `app/telegram/forward_service.py` |
| دریافت پیام جدید کانال | `app/telegram/auto_forward.py` |
| ذخیره نتیجه و شمارنده‌های عملیات | `app/services/forward_results.py` |
| پرس‌وجوی دیتابیس | فایل مربوط به موجودیت در `app/database/repositories/` |

مسیرهای import عمومی `app.ui.messages`، `app.ui.keyboards` و
`app.database.repository` حفظ شده‌اند؛ پیاده‌سازی هر بخش در فایل‌های تخصصی قرار دارد.

## ۳. محدودیت‌های واقعی Telegram

قبل از پیاده‌سازی، این محدودیت‌ها بررسی و در معماری لحاظ شدند:

- **Bot API نمی‌تواند تاریخچه پیام‌های کانال را بخواند.** یک بات فقط به
  پیام‌هایی دسترسی دارد که مستقیماً برایش ارسال/فوروارد شده باشند (یا اگر
  Admin کانال باشد و پیام جدید بعد از عضویتش ارسال شود). گرفتن پیام با
  Message ID دلخواه از یک کانال قدیمی، از طریق Bot API **ممکن نیست**.
- به همین دلیل برای خواندن پیام با Message ID مشخص و Forward واقعی، از
  **Telethon با یک حساب کاربری واقعی** استفاده شده است. این حساب باید عضو
  کانال مبدأ باشد (برای کانال عمومی کافی است؛ برای کانال خصوصی باید از قبل
  عضو یا از طریق Invite Link اضافه شده باشد).
- برای Forward به کانال مقصد، حساب متصل باید در کانال مقصد **Administrator**
  باشد و دسترسی `Post Messages` را داشته باشد.
- **Protected Content:** اگر کانال مبدأ گزینه "Restrict Saving Content" را
  فعال کرده باشد، Forward آن به کانال دیگر توسط تلگرام مسدود می‌شود
  (`ChatForwardsRestrictedError`). این پروژه چنین پیامی را Forward نمی‌کند؛
  بلکه آن را به‌عنوان `Failed` با دلیل «محتوای محافظت‌شده» ثبت و در گزارش
  نهایی نمایش می‌دهد. **این محدودیت از سمت تلگرام است و هیچ راه‌حلی برای
  دور زدن آن در این پروژه پیاده‌سازی نشده (و نخواهد شد).**
- **FloodWait:** تلگرام برای جلوگیری از Spam، پس از تعداد مشخصی درخواست در
  بازه زمانی کوتاه، خطای FloodWait با یک عدد ثانیه برمی‌گرداند. ربات این خطا
  را می‌گیرد، به همان مدت `asyncio.sleep` می‌کند، و عملیات را خودکار ادامه
  می‌دهد؛ کاربر پیام «باید N ثانیه صبر کنیم» را می‌بیند و برنامه Crash
  نمی‌کند.
- **کانال خصوصی:** خواندن/Forward از کانال خصوصی فقط زمانی ممکن است که حساب
  Telethon از قبل عضو آن کانال باشد؛ ربات نمی‌تواند خودش بدون Invite Link
  به یک کانال خصوصی بپیوندد.
- **Media Group / Album:** تلگرام هنگام Forward یک آلبوم، تمام پیام‌های آن
  آلبوم را با شناسه‌های پیاپی نگه می‌دارد؛ Forward تک‌تک پیام‌های یک آلبوم
  (با `forward_messages` روی هر Message ID) به‌درستی کار می‌کند و توسط
  تلگرام به‌صورت گروه در مقصد نمایش داده می‌شود، به شرطی که تمام شناسه‌های
  آلبوم در بازه/لیست انتخابی کاربر باشند.

## ۴. نصب Python

Python نسخه ۳.۱۲ یا بالاتر لازم است.

- ویندوز: از [python.org](https://www.python.org/downloads/) نصب کنید و
  گزینه «Add Python to PATH» را فعال کنید.
- لینوکس (Debian/Ubuntu):
  ```bash
  sudo apt update && sudo apt install python3.12 python3.12-venv
  ```

## ۵. ساخت Virtual Environment

لینوکس/مک:
```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

ویندوز (PowerShell) — به بند ۲۲ نگاه کنید.

## ۶. نصب Dependencies

```bash
pip install -r requirements.txt
```

برای اجرای تست‌ها:
```bash
pip install -r requirements-dev.txt
```

## ۷. ساخت Bot در BotFather

۱. در تلگرام به [@BotFather](https://t.me/BotFather) پیام دهید.
۲. دستور `/newbot` را بزنید و نام و Username دلخواه را وارد کنید.

## ۸. گرفتن Bot Token

پس از ساخت بات، BotFather یک Token شبیه زیر می‌دهد:
```text
123456789:AAExxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```
این مقدار را در `.env` به‌عنوان `BOT_TOKEN` قرار دهید.

## ۹. گرفتن API ID و API Hash

۱. به آدرس [my.telegram.org](https://my.telegram.org) بروید و با شماره
   تلفن خودتان وارد شوید.
۲. وارد بخش **API Development Tools** شوید.
۳. یک Application جدید بسازید (نام و توضیحات دلخواه).
۴. مقادیر `api_id` و `api_hash` نمایش داده می‌شوند؛ آن‌ها را در `.env` به‌عنوان
   `API_ID` و `API_HASH` قرار دهید.

> ⚠️ این مقادیر متعلق به **حساب کاربری شماست**، نه بات. برای عملیات
> Forward واقعی، همین حساب کاربری (نه بات) باید عضو/ادمین کانال‌ها باشد.

## ۱۰. تنظیم .env

فایل `.env.example` را کپی کرده و به `.env` تغییر نام دهید:

```bash
cp .env.example .env
```

سپس مقادیر `BOT_TOKEN`، `API_ID`، `API_HASH` و `ADMIN_IDS` (شناسه عددی
تلگرام خودتان؛ با پیام دادن به [@userinfobot](https://t.me/userinfobot)
قابل دریافت است) را وارد کنید.

## ۱۱. اضافه کردن ربات به کانال‌ها

- **کانال مبدأ:** حساب کاربری متصل (همان که با API_ID/API_HASH لاگین
  می‌شود) باید عضو کانال مبدأ باشد.
- **کانال مقصد:** همان حساب کاربری باید در کانال مقصد اضافه و
  **Administrator** شود.

## ۱۲. تنظیم Administrator Permissions

در تنظیمات کانال مقصد → Administrators → روی حساب موردنظر → حداقل دسترسی
**Post Messages** را فعال کنید.

## ۱۳. اجرای پروژه

```bash
python main.py
```

## ۱۴. اولین Login به Telethon

در اولین اجرا، چون فایل Session (`sessions/forwarder_session.session`) وجود
ندارد، Telethon در کنسول از شما می‌خواهد:

1. شماره تلفن (با کد کشور، مثل `+98912xxxxxxx`)
2. کد تأییدی که تلگرام برایتان ارسال می‌کند
3. رمز عبور Two-Step Verification (در صورت فعال بودن)

پس از این مرحله، فایل Session ساخته می‌شود و در اجراهای بعدی نیازی به Login
مجدد نیست.

## ۱۵. استفاده از Dashboard

پس از اجرای ربات، در تلگرام به بات خود `/start` بزنید. اگر شناسه شما در
`ADMIN_IDS` باشد، Dashboard اصلی نمایش داده می‌شود؛ در غیر این صورت پیام
«دسترسی غیرمجاز» دریافت می‌کنید.

از دکمه‌های Inline برای تنظیم کانال مبدأ/مقصد، شروع انتقال، مشاهده آمار و
تنظیمات استفاده کنید. نیازی به هیچ Command دیگری نیست.

## ۱۶. Forward کردن اولین پیام

۱. از Dashboard، «📥 کانال مبدأ» را بزنید و `@channel` یا `-100xxxxxxxxxx`
   را ارسال کنید.
۲. «📤 کانال مقصد» را همین‌طور تنظیم کنید (ربات باید در آن Administrator
   باشد).
۳. «🚀 انتقال پیام‌ها» → «🔢 انتقال بازه پیام‌ها» → شروع و پایان Message ID
   را وارد کنید.
۴. خلاصه عملیات و سپس صفحه تأیید نهایی را بررسی و «🚀 بله، شروع کن» را
   بزنید.
۵. Progress زنده نمایش داده می‌شود و در پایان گزارش کامل (موفق/ناموفق/
   تکراری) نشان داده می‌شود.

## ۱۷. مدیریت FloodWait

اگر تلگرام FloodWait برگرداند، ربات به‌صورت خودکار پیام «باید N ثانیه صبر
کنیم» را نمایش می‌دهد، `sleep` می‌کند و بدون دخالت کاربر ادامه می‌دهد.

## ۱۸. خطاهای رایج

| خطا | دلیل احتمالی | راه‌حل |
|---|---|---|
| «کانال یافت نشد» | Username اشتباه یا حساب Telethon عضو کانال خصوصی نیست | Username/ID را بررسی کنید یا ابتدا با همان حساب عضو کانال شوید |
| «دسترسی کافی نیست» (مقصد) | حساب متصل Administrator کانال مقصد نیست یا دسترسی ارسال پیام ندارد | در تنظیمات کانال، دسترسی Post Messages را فعال کنید |
| «محتوای محافظت‌شده» | کانال مبدأ Restrict Saving Content فعال دارد | این محدودیت از سمت تلگرام است؛ قابل دور زدن نیست |
| توقف طولانی هنگام انتقال | FloodWait فعال شده | صبر کنید؛ ربات خودکار ادامه می‌دهد |
| ورود دوباره درخواست می‌شود | فایل Session حذف/خراب شده | دوباره طبق بند ۱۴ Login کنید |

## ۱۹. Backup Database و Session

```bash
# لینوکس/مک
cp data/forwarder.db backup/forwarder-$(date +%F).db
cp -r sessions backup/sessions-$(date +%F)
```
```powershell
# ویندوز PowerShell
Copy-Item data\forwarder.db "backup\forwarder-$(Get-Date -Format yyyy-MM-dd).db"
Copy-Item sessions "backup\sessions-$(Get-Date -Format yyyy-MM-dd)" -Recurse
```

فایل Session معادل دسترسی کامل به حساب تلگرام شماست؛ آن را هرگز در جایی
عمومی قرار ندهید یا Commit نکنید (در `.gitignore` قرار دارد).

## ۲۰. اجرای Production

- از `systemd` (لینوکس) یا Task Scheduler/NSSM (ویندوز) برای اجرای همیشگی
  `python main.py` استفاده کنید.
- `LOG_LEVEL=INFO` را در Production نگه دارید و لاگ‌ها را از نظر خطا
  (`logs/error.log`) پایش کنید.
- به‌صورت دوره‌ای از `data/forwarder.db` و پوشه `sessions/` Backup بگیرید.

نمونه سرویس systemd:
```ini
[Unit]
Description=Telegram Forwarder Bot
After=network.target

[Service]
WorkingDirectory=/opt/telegram-forwarder
ExecStart=/opt/telegram-forwarder/.venv/bin/python main.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

## ۲۱. تست‌ها

```bash
pip install -r requirements-dev.txt
pytest -q
python -m ruff check app tests main.py
python -m ruff format --check app tests main.py
```

تنظیمات قالب‌بندی و بررسی کد در `pyproject.toml` است. برای اعمال قالب‌بندی:
`python -m ruff format app tests main.py`.
تست‌ها دیتابیس موقت مستقل می‌سازند و AI و پروکسی را غیرفعال می‌کنند تا به
داده‌های واقعی پروژه یا سرویس خارجی وابسته نباشند.

تمام تست‌ها Mock شده‌اند و به اتصال واقعی تلگرام نیاز ندارند. موارد پوشش‌
داده‌شده: Admin authorization، اعتبارسنجی کانال، اعتبارسنجی Message ID،
تشخیص پیام تکراری، ساخت Job، وضعیت Forward، Retry پیام‌های ناموفق، آمار و
بارگذاری Configuration.

## ۲۲. ویندوز (PowerShell)

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
python main.py
```

---

## سناریوی تست کامل (End-to-End)

1. `.env` را با `BOT_TOKEN`, `API_ID`, `API_HASH`, `ADMIN_IDS` پر کنید.
2. `python main.py` را اجرا کنید و در اولین اجرا Telethon را Login کنید.
3. در تلگرام به بات `/start` بزنید → Dashboard باید نمایش داده شود.
4. کانال مبدأ (کانالی که حساب Telethon عضو آن است) را تنظیم کنید → پیام
   تأیید با نام/ID/Username کانال باید نمایش داده شود.
5. کانال مقصد (کانالی که حساب Telethon در آن Admin است) را تنظیم کنید →
   در صورت نبود دسترسی، پیام «دسترسی کافی نیست» و دکمه «بررسی مجدد» باید
   دیده شود؛ پس از افزودن دسترسی Post Messages و زدن «بررسی مجدد»، تأیید
   می‌شود.
6. «🚀 انتقال پیام‌ها» → «🔢 انتقال بازه پیام‌ها» → یک بازه کوچک (مثلاً ۳ تا
   ۵ پیام واقعی موجود در کانال مبدأ) وارد کنید.
7. صفحه خلاصه و سپس صفحه تأیید نهایی را ببینید و تأیید کنید.
8. پیام Progress باید به‌صورت زنده (با ویرایش همان پیام) به‌روزرسانی شود.
9. پس از پایان، گزارش نهایی (موفق/تکراری/ناموفق) نمایش داده شود؛ به کانال
   مقصد سر بزنید و ببینید پیام‌ها با برچسب «Forwarded from» واقعی منتقل
   شده‌اند (نه کپی متن).
10. همان بازه را دوباره اجرا کنید → همه پیام‌ها باید «تکراری» گزارش شوند و
    دوباره ارسال نشوند.
11. یک Message ID نامعتبر (مثلاً پیام حذف‌شده) را در بازه قرار دهید → باید
    در گزارش نهایی به‌عنوان «ناموفق» ثبت شود و عملیات کل متوقف نشود؛ سپس از
    «🔄 Retry موارد ناموفق» استفاده کنید.
12. حین یک انتقال طولانی، «⏸ توقف» را بزنید → عملیات باید Graceful متوقف
    شود و وضعیت در دیتابیس ذخیره شود؛ سپس «▶️ ادامه» عملیات را از همان نقطه
    ادامه دهد.
13. برنامه را در وسط یک Job ببندید (Ctrl+C) و دوباره اجرا کنید → پیام‌های
    قبلاً موفق دوباره Forward نشوند (بررسی از طریق «📊 آمار»).
14. با یک User ID خارج از `ADMIN_IDS` به بات `/start` بزنید → باید پیام
    «🔒 دسترسی غیرمجاز» دریافت شود و هیچ دکمه‌ای در دسترس نباشد.
