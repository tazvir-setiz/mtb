# شروع اجرای پیاده‌سازی Guard

این فایل نقطه‌ی شروع اجرای کار است. قبل از هر تغییر کد، آن را کامل بخوان و سپس اسناد ارجاع‌شده را به‌ترتیب مطالعه کن.

## دستور مستقیم

از همین حالا پیاده‌سازی بهبود Guard را در همین repository شروع کن. فقط گزارش یا plan تحویل نده؛ کد، تست و مستندات لازم را واقعاً تغییر بده.

## ترتیب مطالعه

1. `docs/guard-start-here.md`
2. `docs/guard-implementation-checklist.md`
3. `docs/guard-implementation-brief.md`
4. `docs/guard-architecture-v2.md`
5. تست‌ها و فایل‌های کدی که در اسناد بالا معرفی شده‌اند

## هدف اجرا

Guard فعلی را به یک pipeline فیلترپذیر، قابل تنظیم، type-safe و قابل تست تبدیل یا تکمیل کن؛ بدون حذف یا تضعیف این قابلیت‌ها:

- `fallback model`
- `circuit breaker`
- budget و deadline
- fail-closed
- grounding
- rewrite
- `Policy Judge`
- `Meaning Judge`
- احراز هویت فعلی مدیر
- جلوگیری از forward تکراری

الگوی فیلتر زنجیره‌ای پروژه `Heavrnl/TelegramForwarder` فقط منبع الهام است. پروژه را کپی یا از صفر بازنویسی نکن؛ با معماری فعلی ادغام surgical انجام بده.

## الزام مهم: تغییر ساده‌ی قوانین Guard

قوانین Guard باید از یک محل متمرکز مانند `GuardProfile` یا ساختار موجود معادل آن قابل تغییر باشند. کاربر باید بتواند حالت دسته‌های زیر را بدون ویرایش چند فایل کد تغییر دهد:

- political
- abuse
- hate
- threat
- sexual
- spam
- injection
- links
- media

فعال/غیرفعال‌کردن rule یا تغییر mode نباید fail-open ایجاد کند. تغییر policy، مدل یا pipeline باید cache و draft خودکار قبلی را invalid کند. تنظیمات فقط از مسیر مجاز مدیریتی قابل تغییر باشد و AI هرگز مجوز تغییر policy یا انتشار را نداشته باشد.

## قواعد ایمنی و معماری

- AI فقط signal یا draft تولید می‌کند؛ تصمیم نهایی را Python و policy می‌سازند.
- خطای AI، timeout، خروجی نامعتبر و provider unavailable هرگز نباید متن خام را publish کنند.
- متن Telegram، خبر و retrieval، داده‌ی untrusted هستند نه instruction.
- `Auth Guard` و `Content Guard` جدا بمانند.
- متن اصلی overwrite نشود.
- rewrite قبل از انتشار هم از نظر policy و هم از نظر meaning بررسی شود.
- media بررسی‌نشده باید صریحاً `REVIEW` یا `RETRY_PENDING` شود و نباید تأیید کامل پیام اعلام شود.
- از dependency غیرضروری، catch خاموش، `as any` و تغییرات نامرتبط پرهیز کن.

## روند اجرا

1. `git status` را بررسی کن و تغییرات کاربر را revert نکن.
2. تست‌های موجود را به‌عنوان baseline اجرا کن.
3. checklist را با وضعیت واقعی به‌روزرسانی کن.
4. ابتدا قراردادها و نقاط اتصال را مشخص کن، سپس کد را تغییر بده.
5. تست‌های targeted برای رفتار تغییرکرده اضافه کن.
6. تست‌های مرتبط و سپس suite موجود را اجرا کن.
7. `git diff --check` و بازبینی diff را انجام بده.
8. فقط فایل‌های مرتبط با این کار را commit کن.

## تحویل بین عامل‌ها یا محدودیت context

اگر کار کامل نشد:

- در `docs/guard-implementation-checklist.md` بخش «وضعیت تحویل» را با وضعیت دقیق پر کن.
- آخرین مرحله‌ی سالم، فایل‌های تغییرکرده، تست‌ها، خطاها و دستور ادامه را بنویس.
- تغییرات سالم را در یک commit کوچک و موضوعی ثبت کن.
- عامل بعدی باید از checklist ادامه دهد، نه اینکه baseline یا طراحی را بی‌دلیل از صفر تکرار کند.

## پایان کار

کار فقط وقتی کامل است که:

- checklist به‌روز شده باشد؛
- تست‌ها پاس شده باشند یا خطاهای pre-existing جدا ثبت شده باشند؛
- مستندات تنظیم‌پذیری Guard به‌روز باشند؛
- diff بدون خطای whitespace باشد؛
- secret و فایل موقت وارد commit نشده باشد؛
- commit با پیام موضوعی و trailer زیر ساخته شده باشد:

```text
Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>
```

