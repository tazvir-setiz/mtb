# چک‌لیست اجرای بهبود Guard

این فایل برای تحویل کار بین عامل‌ها یا ادامه‌ی کار پس از محدودیت context استفاده می‌شود. عامل بعدی باید ابتدا این فایل و سپس `docs/guard-implementation-brief.md` را بخواند.

## قرارداد وضعیت

- `[ ]` انجام نشده
- `[~]` در حال انجام
- `[x]` انجام شده و validation دارد
- `[!]` مسدود یا نیازمند تصمیم

قانون مهم: هر مرحله‌ای که `[x]` می‌شود باید فایل‌های تغییرکرده، تست اجراشده و نتیجه‌ی کوتاه داشته باشد. اگر محدودیت خوردی، وضعیت را همین‌جا ثبت کن و commit مرحله‌ای بساز؛ کار را از صفر شروع نکن.

## شروع و baseline

- [x] وضعیت git و تغییرات کاربر بررسی شد؛ تغییرات کاربر revert نمی‌شود.
- [x] `docs/guard-implementation-brief.md` خوانده شد.
- [x] مسیر `moderation_service -> GuardPipeline -> forwarding` trace شد.
- [x] تست‌های baseline اجرا و نتیجه ثبت شد.
- [x] dependency یا migration جدید فقط پس از اثبات ضرورت انتخاب شد.

یادداشت اجرا:

```text
Baseline command: .\.venv\Scripts\python.exe -m pytest
Baseline result: 427 passed, 20624 warnings
Current command: .\.venv\Scripts\python.exe -m pytest
Current result: 441 passed, 21848 warnings
```

## طراحی و قرارداد

- [x] قرارداد `MessageContext` موجود بررسی و در صورت امکان reuse شد.
- [x] قرارداد خروجی فیلترها و reason codeها مشخص شد.
- [x] `PUBLISH / DROP / REVIEW / RETRY_PENDING` از label مدل جدا نگه داشته شد.
- [x] اصل پیام، متن normalized و متن انتشار جدا هستند.
- [x] `media_checked` یا معادل آن صریح است.
- [x] policy و pipeline version در fingerprint حضور دارند.

## زنجیره فیلتر

- [x] آماده‌سازی ورودی مستقل است.
- [x] source/destination policy از content moderation جداست.
- [x] ruleهای محلی در `rule_guard` متمرکز باقی مانده‌اند.
- [x] keyword به‌تنهایی نفی، نقل‌قول یا آموزش را حذف نمی‌کند.
- [x] prompt injection signal مستقل دارد.
- [x] media ناشناخته یا بررسی‌نشده fail-open نمی‌شود.
- [x] ترتیب filterها در تست پوشش داده شده است.

## قابل تنظیم بودن Guard

- [x] یک محل اصلی برای `GuardProfile` و policy وجود دارد.
- [x] فعال/غیرفعال‌کردن دسته‌ها بدون ویرایش کد ممکن است.
- [x] حالت هر دسته مستقل قابل تغییر است.
- [x] دسته‌های زیر قابل تنظیم‌اند:
  - [x] سیاسی
  - [x] abuse
  - [x] hate
  - [x] threat
  - [x] sexual
  - [x] spam
  - [x] injection
  - [x] link
  - [x] media
- [x] prompt سفارشی و ruleهای پایه نسخه‌دار هستند.
- [x] تغییر policy، cache و draft خودکار قبلی را invalid می‌کند.
- [x] تغییر تنظیمات فقط برای کاربر مجاز ممکن است.
- [x] خاموش‌کردن rule باعث انتشار خودکار محتوای نامطمئن نمی‌شود.
- [x] راهنمای تغییر Guard در مستندات یا UI روشن است.

## ارتباط با AI

- [x] stageهای فعلی حفظ و از handlerها جدا هستند.
- [x] system prompt و داده‌ی کاربر جدا هستند.
- [x] Telegram/news/retrieval به‌عنوان untrusted data علامت‌گذاری می‌شوند.
- [x] مدل امکان اجرای publish، forward یا تغییر تنظیمات ندارد.
- [x] schema هر stage با validator مستقل بررسی می‌شود.
- [x] evidence باید در متن اصلی وجود داشته باشد.
- [x] timeout، provider error و invalid output fail-closed هستند.
- [x] fallback و circuit breaker فعلی خراب نشده‌اند.
- [x] rewrite قبل از انتشار policy و meaning verification دارد.

## lifecycle و retry

- [x] وضعیت‌های پردازش قابل ردیابی هستند.
- [x] `PENDING_REVIEW` از `RETRY_PENDING` متمایز است.
- [x] retry محدود و قابل ردیابی است.
- [x] retry باعث forward دوباره نمی‌شود.
- [x] draft و callback قدیمی روی نسخه‌ی جدید اثر نمی‌گذارند.
- [x] تصمیم دستی مدیر از تصمیم خودکار جداست.

## Clean Code و کیفیت

- [x] هر تابع مسئولیت مشخص دارد.
- [x] منطق تکراری استخراج یا reuse شده است.
- [x] handlerها فقط orchestration می‌کنند.
- [x] type/dataclass قراردادها روشن است.
- [x] catch عمومی بدون log وجود ندارد.
- [x] secret، متن خصوصی کامل و prompt خام در log ثبت نمی‌شود.
- [x] dependency غیرضروری اضافه نشده است.
- [x] فایل نامرتبط تغییر نکرده است.

## تست‌های پذیرش

- [x] پیام سالم
- [x] پیام مبهم
- [x] keyword در نفی
- [x] نقل‌قول آموزشی
- [x] فحاشی محض
- [x] prompt injection
- [x] پیام سیاسی خنثی
- [x] خطای AI و timeout
- [x] fallback model
- [x] rewrite با تغییر معنا
- [x] rewrite دارای HTML/link خطرناک
- [x] خروجی نامعتبر مدل
- [x] رسانه‌ی بررسی‌نشده
- [x] invalid شدن cache پس از تغییر policy
- [x] authorization کاربر غیرمجاز
- [x] جلوگیری از forward تکراری

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

