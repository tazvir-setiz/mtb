# دیپلوی روی Railway

این پروژه یک سرویس دائمی با Telegram long polling است. وب‌سرور، دامنه عمومی،
Webhook یا پورت ورودی لازم ندارد. Dockerfile ریشه پروژه Python 3.12 و وابستگی‌ها
را نصب می‌کند و `python -u main.py` را اجرا می‌کند.

## ۱. آماده‌سازی Session روی کامپیوتر خودتان

ابتدا ربات محلی را متوقف کنید. `.env` محلی باید `BOT_TOKEN`، `API_ID`، `API_HASH`
و `ADMIN_IDS` معتبر داشته باشد. از ریشه پروژه اجرا کنید:

```powershell
.venv\Scripts\python.exe -m scripts.export_session
```

در لینوکس/مک: `python -m scripts.export_session`.
اگر قبلاً وارد حساب نشده باشید، در همین ترمینال شماره، کد ورود و در صورت نیاز
رمز دومرحله‌ای را وارد می‌کنید. از حساب کاربری عضو کانال مبدأ و دارای اجازه ارسال
در مقصد استفاده کنید.

خروجی در `sessions/railway-session.txt` ذخیره می‌شود؛ مقدار حساس در ترمینال چاپ
نمی‌شود. محتوای فایل را فقط در متغیر `TELETHON_STRING_SESSION` سرویس Railway بگذارید.
این فایل و Sessionها در Git و Docker build context وارد نمی‌شوند. این رشته معادل
مجوز ورود حساب است و نباید در مخزن یا گفتگو منتشر شود.

اگر فایل خروجی از قبل وجود داشته باشد، اسکریپت آن را بازنویسی نمی‌کند. برای گرفتن
خروجی تازه، فایل قبلی را جابه‌جا یا حذف کنید. پس از انتقال به Railway، ربات محلی
را هم‌زمان با همان توکن و Session اجرا نکنید.

## ۲. ساخت سرویس و فضای دائمی

1. فایل‌های پروژه را در مخزن GitHub خود قرار دهید و در Railway یک سرویس از آن مخزن
   بسازید. Root Directory باید پوشه‌ای باشد که `Dockerfile` و `main.py` داخل آن هستند.
2. یک Volume به **همین سرویس** متصل کنید و Mount Path را دقیقاً `/data` قرار دهید.
3. قبل از اجرای نهایی، متغیرهای بخش بعد و تنظیمات سرویس را ثبت کنید.

فایل دیتابیس `/data/forwarder.db` و فایل ورود `/data/forwarder_session.session`
روی Volume نگهداری می‌شوند. ساخت جدول‌ها هنگام شروع برنامه انجام می‌شود؛
Pre-deploy Command لازم نیست. Volume را در دیپلوی‌های بعدی نگه دارید و برای آن
Backup تنظیم کنید. [مستندات Volume](https://docs.railway.com/volumes)

## ۳. متغیرهای محیطی

از `.env.railway.example` به‌عنوان الگو برای بخش Variables سرویس استفاده کنید.
مقادیر خالی مربوط به اعتبارنامه‌ها باید با مقادیر واقعی جایگزین شوند:

| متغیر | مقدار |
|---|---|
| `BOT_TOKEN` | توکن BotFather |
| `API_ID` | API ID عددی حساب کاربری |
| `API_HASH` | API Hash همان حساب |
| `ADMIN_IDS` | شناسه عددی مدیر، یا چند شناسه با کاما |
| `TELETHON_STRING_SESSION` | محتوای فایل خروجی مرحله اول، بدون نقل‌قول اضافه |
| `DATABASE_URL` | `sqlite:////data/forwarder.db`؛ چهار `/` بعد از `sqlite:` |
| `TELETHON_SESSION` | `/data/forwarder_session` |
| `PROXY_ENABLED` | `false` |
| `LOG_TO_FILE` | `false`؛ لاگ‌ها در خروجی Railway دیده می‌شوند |
| `LOG_LEVEL` | `INFO` |
| `FORWARD_DELAY` | `1.5` |
| `PROGRESS_UPDATE_INTERVAL` | `3` |
| `AI_ENABLED` | ابتدا `false`؛ در صورت نیاز بعداً فعال کنید |

برای AI، متغیرهای `AI_API_KEY`، `AI_BASE_URL`، `AI_MODEL` و `AI_GUARDRAILS` را
تنظیم کنید و سپس `AI_ENABLED=true` بگذارید. کلیدها را فقط در Variables ذخیره کنید.
تنظیم پروکسی محلی مثل `127.0.0.1:12334` روی Railway به کامپیوتر شما وصل نمی‌شود.

Session رشته‌ای فقط در اولین اجرا، وقتی فایل Session هنوز کلید ورود ندارد،
داخل SQLite Session وارد می‌شود. بعد از آن فایل روی Volume مرجع ورود است و
کش کانال‌ها نیز در همان فایل باقی می‌ماند. مقدار تازه در Variables به‌تنهایی
Session قبلی را عوض نمی‌کند. [مستندات Session در Telethon](https://docs.telethon.dev/en/stable/concepts/sessions.html)

## ۴. تنظیمات سرویس Railway

| تنظیم | مقدار |
|---|---|
| Builder | Dockerfile ریشه پروژه |
| Start Command | خالی؛ دستور `CMD` داخل Dockerfile استفاده می‌شود |
| Pre-deploy Command | خالی |
| Healthcheck Path | خالی؛ این برنامه endpoint HTTP ندارد |
| Replicas | `1`، در یک Region |
| Serverless / App Sleeping | غیرفعال؛ ربات باید دائماً پیام دریافت کند |
| Restart Policy | `On Failure`، با حداکثر ۱۰ تلاش |
| Public Networking | نیازی به ساخت Domain نیست |

طبق مستندات فعلی Railway، `railway.json` و `railway.toml` برای سرویس‌های جدید
قابل فعال‌سازی نیستند. این پروژه از Dockerfile و تنظیمات بالا استفاده می‌کند.
اگر بعداً مدیریت پروژه با کد لازم شد، مسیر جدید Railway، Infrastructure as Code است.
[مستندات رسمی](https://docs.railway.com/infrastructure-as-code)

نبود Healthcheck یعنی وضعیت Active در Railway به‌تنهایی اتصال تلگرام را تأیید
نمی‌کند؛ لاگ و پاسخ `/start` را هم بررسی کنید.
[رفتار Healthcheck](https://docs.railway.com/deployments/healthchecks)

## ۵. اولین اجرا و بررسی

1. Deploy کنید و در لاگ‌ها پیام `Telethon client متصل شد.` را بررسی کنید.
2. از حساب مدیر در تلگرام `/start` بفرستید.
3. کانال مبدأ و مقصد را تنظیم کنید و یک انتقال آزمایشی انجام دهید.
4. برای انتقال خودکار، گزینه Auto-Forward را در داشبورد روشن کنید.
5. یک Restart انجام دهید و باقی ماندن کانال‌ها و تنظیمات را بررسی کنید.

دیتابیس محلی به‌صورت خودکار آپلود نمی‌شود؛ Volume جدید با داده‌های خالی شروع می‌شود.
برای حفظ داده‌های قبلی، هر دو سرویس را متوقف کنید، از دیتابیس و فایل Session محلی
Backup بگیرید و با ابزار مدیریت فایل Volume در Railway آن‌ها را با نام‌های بالا
به `/data` منتقل کنید. سپس فقط سرویس Railway را اجرا کنید.

## خطاهای رایج

| خطا | اقدام |
|---|---|
| `interactive login is unavailable` | Session معتبر را از کامپیوتر محلی بسازید و در Variables بگذارید |
| `Invalid TELETHON_STRING_SESSION` | رشته کامل و بدون نقل‌قول یا فاصله اضافی را وارد کنید |
| Session قبلی لغو شده است | سرویس را متوقف کنید؛ فایل‌های `forwarder_session.session*` همان Session را از Volume کنار بگذارید، رشته جدید را تنظیم و دوباره Deploy کنید؛ دیتابیس `forwarder.db` را نگه دارید |
| تنظیمات بعد از Deploy پاک می‌شوند | Volume و مسیر `/data` و مقدار `DATABASE_URL` را بررسی کنید |
| `Conflict: terminated by other getUpdates request` | ربات محلی یا Replica اضافه را متوقف کنید |
| اتصال به `127.0.0.1` شکست می‌خورد | `PROXY_ENABLED=false` را تنظیم کنید |

برای جلوگیری از توقف روی درخواست کد ورود، برنامه در محیط بدون ترمینال، نبود
Session معتبر را با خطای مشخص گزارش می‌کند و خارج می‌شود.

## بررسی محلی قبل از انتشار

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m ruff check app scripts tests main.py
.venv\Scripts\python.exe -m ruff format --check app scripts tests main.py
docker build -t telegram-forwarder .
```

ساخت Image هیچ توکن یا Session واقعی نیاز ندارد. اجرای کانتینر با اعتبارنامه‌های
واقعی، ربات را فعال می‌کند؛ برای آن همان محدودیت یک اجرای هم‌زمان را رعایت کنید.
