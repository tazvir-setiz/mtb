# چک‌لیست اجرای بهبود Guard

این فایل برای تحویل کار بین عامل‌ها یا ادامه‌ی کار پس از محدودیت context استفاده می‌شود. عامل بعدی باید ابتدا این فایل و سپس `docs/guard-implementation-brief.md` را بخواند.

## قرارداد وضعیت

- `[ ]` انجام نشده
- `[~]` در حال انجام
- `[x]` انجام شده و validation دارد
- `[!]` مسدود یا نیازمند تصمیم

قانون مهم: هر مرحله‌ای که `[x]` می‌شود باید فایل‌های تغییرکرده، تست اجراشده و نتیجه‌ی کوتاه داشته باشد. اگر محدودیت خوردی، وضعیت را همین‌جا ثبت کن و commit مرحله‌ای بساز؛ کار را از صفر شروع نکن.

## شروع و baseline

- [ ] وضعیت git و تغییرات کاربر بررسی شد؛ تغییرات کاربر revert نمی‌شود.
- [ ] `docs/guard-implementation-brief.md` خوانده شد.
- [ ] مسیر `moderation_service -> GuardPipeline -> forwarding` trace شد.
- [ ] تست‌های baseline اجرا و نتیجه ثبت شد.
- [ ] dependency یا migration جدید فقط پس از اثبات ضرورت انتخاب شد.

یادداشت اجرا:

```text
Baseline command:
Baseline result:
Current commit:
```

## طراحی و قرارداد

- [ ] قرارداد `MessageContext` موجود بررسی و در صورت امکان reuse شد.
- [ ] قرارداد خروجی فیلترها و reason codeها مشخص شد.
- [ ] `PUBLISH / DROP / REVIEW / RETRY_PENDING` از label مدل جدا نگه داشته شد.
- [ ] اصل پیام، متن normalized و متن انتشار جدا هستند.
- [ ] `media_checked` یا معادل آن صریح است.
- [ ] policy و pipeline version در fingerprint حضور دارند.

## زنجیره فیلتر

- [ ] آماده‌سازی ورودی مستقل است.
- [ ] source/destination policy از content moderation جداست.
- [ ] ruleهای محلی در `rule_guard` متمرکز باقی مانده‌اند.
- [ ] keyword به‌تنهایی نفی، نقل‌قول یا آموزش را حذف نمی‌کند.
- [ ] prompt injection signal مستقل دارد.
- [ ] media ناشناخته یا بررسی‌نشده fail-open نمی‌شود.
- [ ] ترتیب filterها در تست پوشش داده شده است.

## قابل تنظیم بودن Guard

- [ ] یک محل اصلی برای `GuardProfile` و policy وجود دارد.
- [ ] فعال/غیرفعال‌کردن دسته‌ها بدون ویرایش کد ممکن است.
- [ ] حالت هر دسته مستقل قابل تغییر است.
- [ ] دسته‌های زیر قابل تنظیم‌اند:
  - [ ] سیاسی
  - [ ] abuse
  - [ ] hate
  - [ ] threat
  - [ ] sexual
  - [ ] spam
  - [ ] injection
  - [ ] link
  - [ ] media
- [ ] prompt سفارشی و ruleهای پایه نسخه‌دار هستند.
- [ ] تغییر policy، cache و draft خودکار قبلی را invalid می‌کند.
- [ ] تغییر تنظیمات فقط برای کاربر مجاز ممکن است.
- [ ] خاموش‌کردن rule باعث انتشار خودکار محتوای نامطمئن نمی‌شود.
- [ ] راهنمای تغییر Guard در مستندات یا UI روشن است.

## ارتباط با AI

- [ ] stageهای فعلی حفظ و از handlerها جدا هستند.
- [ ] system prompt و داده‌ی کاربر جدا هستند.
- [ ] Telegram/news/retrieval به‌عنوان untrusted data علامت‌گذاری می‌شوند.
- [ ] مدل امکان اجرای publish، forward یا تغییر تنظیمات ندارد.
- [ ] schema هر stage با validator مستقل بررسی می‌شود.
- [ ] evidence باید در متن اصلی وجود داشته باشد.
- [ ] timeout، provider error و invalid output fail-closed هستند.
- [ ] fallback و circuit breaker فعلی خراب نشده‌اند.
- [ ] rewrite قبل از انتشار policy و meaning verification دارد.

## lifecycle و retry

- [ ] وضعیت‌های پردازش قابل ردیابی هستند.
- [ ] `PENDING_REVIEW` از `RETRY_PENDING` متمایز است.
- [ ] retry محدود و قابل ردیابی است.
- [ ] retry باعث forward دوباره نمی‌شود.
- [ ] draft و callback قدیمی روی نسخه‌ی جدید اثر نمی‌گذارند.
- [ ] تصمیم دستی مدیر از تصمیم خودکار جداست.

## Clean Code و کیفیت

- [ ] هر تابع مسئولیت مشخص دارد.
- [ ] منطق تکراری استخراج یا reuse شده است.
- [ ] handlerها فقط orchestration می‌کنند.
- [ ] type/dataclass قراردادها روشن است.
- [ ] catch عمومی بدون log وجود ندارد.
- [ ] secret، متن خصوصی کامل و prompt خام در log ثبت نمی‌شود.
- [ ] dependency غیرضروری اضافه نشده است.
- [ ] فایل نامرتبط تغییر نکرده است.

## تست‌های پذیرش

- [ ] پیام سالم
- [ ] پیام مبهم
- [ ] keyword در نفی
- [ ] نقل‌قول آموزشی
- [ ] فحاشی محض
- [ ] prompt injection
- [ ] پیام سیاسی خنثی
- [ ] خطای AI و timeout
- [ ] fallback model
- [ ] rewrite با تغییر معنا
- [ ] rewrite دارای HTML/link خطرناک
- [ ] خروجی نامعتبر مدل
- [ ] رسانه‌ی بررسی‌نشده
- [ ] invalid شدن cache پس از تغییر policy
- [ ] authorization کاربر غیرمجاز
- [ ] جلوگیری از forward تکراری

## تحویل مرحله‌ای پس از محدودیت

اگر context یا زمان تمام شد:

1. کار ناتمام را در بخش «وضعیت تحویل» ثبت کن.
2. تست‌های همان مرحله را اجرا کن.
3. تغییرات سالم را commit کن.
4. در commit فقط یک موضوع منطقی را قرار بده.
5. فایل‌های تغییرکرده و دستور ادامه را ثبت کن.

قالب وضعیت تحویل:

```text
آخرین مرحله کامل:
مرحله فعلی:
فایل‌های تغییرکرده:
تست‌های اجراشده:
نتیجه تست:
کار باقی‌مانده:
ریسک یا تصمیم لازم:
دستور شروع ادامه کار:
```

## پیش از commit نهایی

- [ ] تمام موارد ضروری بالا `[x]` یا با دلیل در `[!]` هستند.
- [ ] تست‌های مرتبط پاس شده‌اند.
- [ ] suite موجود پروژه پاس شده یا خطاهای pre-existing جدا ثبت شده‌اند.
- [ ] `git diff --check` پاس شده است.
- [ ] `git diff` بازبینی شده است.
- [ ] secret یا فایل موقت وارد commit نشده است.
- [ ] مستندات به‌روز هستند.

## دستور commit

پس از تکمیل و validation:

```bash
git add app tests docs
git diff --cached --check
git commit -m "feat(guard): make moderation pipeline configurable" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

اگر کار به چند مرحله تقسیم شد، از commitهای کوچک و موضوعی استفاده کن؛ commit ناقص یا تست‌نشده نساز.

