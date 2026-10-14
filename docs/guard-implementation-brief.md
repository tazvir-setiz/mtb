# سند مرجع پیاده‌سازی Guard

## هدف

Guard فعلی پروژه باید به یک pipeline فیلترپذیر، قابل تنظیم و قابل تست تبدیل شود؛ بدون اینکه قابلیت‌های فعلی مانند `fallback model`، `circuit breaker`، `budget`، `fail-closed`، `grounding`، بازنویسی، `Policy Judge` و `Meaning Judge` حذف یا تضعیف شوند.

الگوی الهام‌بخش، `Heavrnl/TelegramForwarder` است؛ اما این پروژه نباید به یک فیلتر AI ساده تبدیل شود. معماری فعلی `app/services/guard/pipeline.py` مرجع اصلی تصمیم‌گیری باقی می‌ماند.

## قواعد غیرقابل مذاکره

- AI فقط signal و پیشنهاد تولید می‌کند؛ تصمیم نهایی انتشار را کد و policy می‌سازند.
- خطای AI، timeout، خروجی نامعتبر یا provider unavailable نباید به انتشار متن خام منجر شود.
- متن تلگرام، خبر و retrieval داده‌ی غیرقابل‌اعتماد هستند، نه instruction.
- `Auth Guard` از `Content Guard` جدا می‌ماند.
- متن اصلی هرگز overwrite نمی‌شود.
- rewrite فقط پس از بررسی policy و حفظ معنا قابل انتشار است.
- رسانه‌ی بررسی‌نشده نباید به‌عنوان پیام کاملاً تأییدشده گزارش شود.
- تغییرات باید کوچک، type-safe، قابل rollback و مطابق اصول Clean Code باشند.

## ساختار پیشنهادی

پیام از این مسیر عبور می‌کند:

```text
MessageContext
  -> local preparation
  -> source/policy rules
  -> prompt-injection signal
  -> AI analysis
  -> optional grounding
  -> reassessment
  -> meaning decomposition
  -> rewrite
  -> policy judge
  -> meaning judge
  -> local output validation
  -> PUBLISH / DROP / REVIEW / RETRY_PENDING
```

## تنظیم‌پذیری Guard

کاربر باید بتواند بدون ویرایش چند فایل و بدون تغییر کد اصلی، قواعد را تغییر دهد. برای این منظور:

1. قوانین محتوایی در یک `GuardProfile` یا ساختار معادل متمرکز شوند.
2. هر قانون شناسه، عنوان، نوع، وضعیت فعال/غیرفعال و شدت داشته باشد.
3. حساسیت هر دسته مستقل باشد:
   - `political`
   - `abuse`
   - `hate`
   - `threat`
   - `sexual`
   - `spam`
   - `injection`
   - `links`
   - `media`
4. prompt سفارشی، کلمات/عبارت‌ها، دامنه‌های مجاز و محدودیت‌ها از policy جدا ولی در یک snapshot نسخه‌دار جمع شوند.
5. تغییر policy، مدل یا pipeline نسخه‌ی cache و draftهای خودکار قبلی را نامعتبر کند.
6. قوانین پیش‌فرض امن باقی بمانند؛ خاموش‌کردن rule نباید fail-open یا انتشار ناخواسته ایجاد کند.
7. تغییر تنظیمات از مسیرهای موجود پنل و با authorization فعلی انجام شود؛ AI نباید تنظیمات را تغییر دهد.

نمونه‌ی مفهومی تنظیمات:

```json
{
  "rules": {
    "injection": {"mode": "review", "enabled": true},
    "spam": {"mode": "review", "enabled": true},
    "abuse": {"mode": "rewrite_or_drop", "enabled": true},
    "political": {"mode": "review", "enabled": true}
  },
  "media": {
    "unchecked_action": "review"
  },
  "ai": {
    "allow_rewrite": true,
    "allow_grounding": true
  }
}
```

این JSON فقط نمونه‌ی قرارداد است. قبل از اضافه‌کردن schema جدید، `app/guard_config.py`، `app/services/guard_profile.py` و تنظیمات موجود بررسی و reuse شوند.

## فیلترها

اگر abstraction مشابهی وجود ندارد، فیلترهای کوچک با قرارداد مشخص ایجاد شود:

- `InputPreparationFilter`: حفظ اصل، normalization، محدودیت حجم و تشخیص obfuscation.
- `SourcePolicyFilter`: بررسی مبدأ، مقصد و policy محتوا.
- `KeywordRuleFilter`: استفاده از `rule_guard`؛ keyword به‌تنهایی برای حذف محتوای نفی، نقل‌قول یا آموزشی کافی نیست.
- `PromptInjectionFilter`: تشخیص injection به‌صورت signal مستقل.
- `MediaPolicyFilter`: ثبت `media_checked` و ارجاع موارد بررسی‌نشده به `REVIEW` یا `RETRY_PENDING`.
- `AIClassificationFilter`: استفاده از قراردادهای ساختاریافته‌ی فعلی.
- `RewriteVerificationFilter`: اتصال به policy و meaning judge فعلی.

هر فیلتر باید خروجی و reason code مشخص داشته باشد و خطای خود را پنهان نکند.

## قرارداد AI

Stageهای فعلی حفظ شوند:

```text
analyze
reassess
drop_audit
meaning
rewrite
repair
policy_judge
meaning_judge
```

قواعد ارتباط:

- system prompt و user data جدا باشند.
- داده‌ی تلگرام با marker واضح مثل `UNTRUSTED_TELEGRAM_DATA` ارسال شود.
- external evidence با marker جدا ارسال شود.
- خروجی فقط JSON معتبر مطابق schema باشد.
- evidence باید substring واقعی متن اصلی باشد.
- label و confidence مستقیماً action نیستند.
- provider، ابزار یا مدل نباید امکان اجرای forward/publish داشته باشد.

## Clean Code

- هر تابع یک مسئولیت اصلی داشته باشد.
- handler فقط orchestration کند؛ منطق policy داخل handler تکرار نشود.
- نام‌گذاری بر اساس domain باشد، نه جزئیات provider.
- از global state جدید و وابستگی پنهان پرهیز شود.
- قراردادهای داده با dataclass/type مشخص شوند.
- خطاهای قابل انتظار با reason code مشخص مدیریت شوند؛ `except Exception` بدون log یا تبدیل بی‌دلیل ممنوع است.
- از تکرار prompt، validation و decision mapping جلوگیری شود.
- dependency جدید فقط با دلیل فنی و ثبت در مستندات اضافه شود.
- تغییرات نامرتبط انجام نشود.

## تست و معیار پذیرش

حداقل این موارد باید تست شوند:

- سالم‌ها بدون AI و با AI طبق policy درست منتشر شوند.
- keyword در نفی، نقل‌قول و متن آموزشی حذف قطعی ایجاد نکند.
- فحاشی محض قابل حذف باشد.
- injection به‌عنوان data مدیریت شود.
- خطای AI هرگز fail-open نباشد.
- rewrite تغییر نفی، عدد، نام، انتساب یا معنا را رد کند.
- خروجی مدل و evidence نامعتبر reject شود.
- رسانه‌ی بررسی‌نشده به `REVIEW` یا وضعیت معادل برسد.
- تغییر policy، cache قبلی را invalid کند.
- کاربر غیرمجاز نتواند تنظیمات یا review را تغییر دهد.
- retry باعث forward تکراری نشود.

پس از تغییر، تست‌های موجود و تست‌های targeted اجرا شوند. نتیجه‌ی واقعی تست‌ها در گزارش کار ثبت شود.

## Commit

عامل اجراکننده فقط پس از تکمیل تغییرات و عبور validation commit بسازد:

```text
feat(guard): make moderation pipeline configurable

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>
```

قبل از commit:

- `git diff --check`
- تست‌های مرتبط و سپس suite موجود
- بررسی `git diff`
- اطمینان از نبود secret، فایل موقت یا تغییر نامرتبط

