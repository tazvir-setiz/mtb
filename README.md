# MTB — Telegram Forwarder with AI Guard V4.1

ربات MTB پیام‌های تلگرام را از مبدأ مشخص به مقصد مشخص منتقل می‌کند و پیش از انتشار، متن را با یک گارد چندمرحله‌ای بررسی می‌کند. هدف اصلی این نسخه این است که پیام‌های قابل اصلاح را تا حد ممکن به‌صورت خودکار بازنویسی کند، پیام‌های واقعاً نامناسب را حذف کند و فقط موارد واقعاً مبهم را برای بررسی مدیر نگه دارد.

## قابلیت‌های اصلی

- فوروارد خودکار پیام از مبدأ به مقصد
- پنل مدیریت داخل تلگرام
- پاک‌سازی لینک‌ها و آیدی‌ها پیش از انتشار
- بررسی محتوای پیام با AI
- تفکیک «توهین خالص» از «محتوای مفید همراه با توهین»
- بازنویسی خودکار پیام‌های قابل اصلاح
- بررسی مستقل امنیت/سیاست و حفظ معنا بعد از بازنویسی
- یک مرحله repair در صورت ناموفق بودن بازنویسی اول
- صف REVIEW برای موارد واقعاً مبهم، خطای سرویس یا شکست اعتبارسنجی
- کش تصمیم‌ها و context کوتاه‌مدت برای کاهش درخواست‌های غیرضروری
- benchmark ثابت برای regression testing

## معماری Guard V4.1

مسیر اصلی گارد:

```text
Telegram Message
      ↓
Local normalization / rules
      ↓
Analyze
      ↓
Reassess (فقط در ابهام)
      ↓
Independent drop audit (برای DROP)
      ↓
Meaning decomposition
      ↓
Rewrite generation
      ↓
Policy Judge
      ↓
Meaning Judge
      ↓
Repair (در صورت نیاز)
      ↓
Final Policy Judge + Final Meaning Judge
      ↓
SEND / DROP / REVIEW
```

### اصل طراحی

وجود یک کلمه مشکوک به‌تنهایی نباید تصمیم نهایی را تعیین کند. گارد بین این موارد تفاوت می‌گذارد:

1. وجود واژه مشکوک
2. معنی توهین‌آمیز یا نامناسب
3. معنی واقعاً ممنوع
4. معنی سالمی که بعد از حذف بخش نامناسب قابل حفظ است

برای مثال، اگر پیام علاوه بر توهین یک درخواست یا اطلاعات قابل حفظ داشته باشد، مسیر `REWRITE` اجرا می‌شود. اگر کل پیام فقط توهین مستقیم باشد، `ABUSE` و `DROP` می‌شود.

## برچسب‌ها

- `OK` — قابل انتشار بدون تغییر
- `SANITIZE` — فقط پاک‌سازی لینک/آیدی
- `REWRITE` — نیازمند بازنویسی، ولی معنی سالم قابل حفظ است
- `REVIEW` — ابهام واقعی یا شکست مرحله‌ای
- `ABUSE` — توهین مستقیم بدون محتوای مستقل قابل حفظ
- `HATE` — حمله تعمیم‌یافته به یک گروه از افراد
- `THREAT` — تهدید یا ارعاب
- `PORN` — محتوای جنسی صریح طبق سیاست پروژه
- `SPAM` — اسپم/کلاهبرداری/تبلیغ ممنوع
- `INJECTION` — تلاش برای کنترل یا دور زدن گارد
- `POLITICAL` — فقط در صورتی که سیاست سفارشی جداگانه نیاز به بررسی مدیر داشته باشد

## Meaning Decomposition

در پیام‌های قابل بازنویسی، مدل معنی را به چهار بخش تقسیم می‌کند:

- `protected_meaning` — معنی‌هایی که حتماً باید حفظ شوند
- `removable_meaning` — بخش‌هایی که باید حذف یا خنثی شوند
- `entities_relations` — افراد، اشیا، نسبت‌ها و روابط مهم
- `ambiguities` — ابهام‌های واقعی

تمام اعضای این آرایه‌ها باید string باشند.

## بازنویسی و اعتبارسنجی

Classifier هیچ متن جایگزینی تولید نمی‌کند. اگر نتیجه `REWRITE` باشد:

1. Meaning Decomposer معنی قابل حفظ را مشخص می‌کند.
2. Rewrite Generator متن جدید می‌سازد.
3. Policy Judge فقط انتشارپذیری متن جدید را بررسی می‌کند.
4. Meaning Judge بررسی می‌کند که معنی‌های محافظت‌شده حذف یا تغییر نکرده باشند.
5. اگر یکی از judgeها رد کند، یک repair انجام می‌شود.
6. متن repair شده دوباره با هر دو judge بررسی می‌شود.

فقط خروجی‌ای که هر دو judge آن را تأیید کنند خودکار منتشر می‌شود.

## سیاست‌های محتوایی پروژه

این گارد علاوه بر سیاست‌های عمومی abuse/threat/hate/spam/injection، سیاست‌های سفارشی پروژه را نیز از `app/prompts/guardrails.txt` می‌خواند.

### احترام مذهبی

توهین و تحقیر مستقیم نسبت به اسلام، قرآن، پیامبر اسلام، پیامبران، ائمه/اهل‌بیت و شعائر یا مراسم مذهبی طبق سیاست پروژه ممنوع است. در عین حال سؤال، نقد غیرتوهین‌آمیز، بحث تاریخی/علمی، نقل‌قول، گزارش و اشاره به وقوع توهین نباید صرفاً به دلیل موضوع مذهبی حذف شوند.

### موضوعات سیاسی و مسئولان عمومی

گارد نباید صرفاً به دلیل موضع سیاسی پیام تصمیم بگیرد. حمایت یا مخالفت سیاسی، نقد دولت‌ها و ایدئولوژی‌ها، حمایت از مردم فلسطین، و ذکر/گزارش/تحلیل سازمان‌ها به‌خودی‌خود تخلف نیست. توهین شخصی، لقب تحقیرآمیز، تهدید و حمله گروهی با همان قواعد عادی بررسی می‌شوند. ادعاهای جدی درباره اشخاص مشخص، وقتی به‌صورت واقعیت قطعی و بدون منبع یا انتساب کافی مطرح شوند، می‌توانند به REVIEW بروند. این قاعده نسبت به همه طرف‌های سیاسی به‌صورت یکسان اعمال می‌شود.

## نصب

Python پیشنهادی: نسخه سازگار با dependencyهای پروژه.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

برای اجرای تست‌های توسعه:

```powershell
pip install -r requirements-dev.txt
```

## تنظیمات محیط

فایل نمونه:

```text
.env.example
```

آن را به `.env` کپی کنید و حداقل این مقادیر را تنظیم کنید:

```env
BOT_TOKEN=...
API_ID=...
API_HASH=...
ADMIN_IDS=...
DATABASE_URL=sqlite:///data/forwarder.db
TELETHON_SESSION=sessions/forwarder_session

AI_ENABLED=true
AI_API_KEY=...
AI_BASE_URL=https://api.openai.com/v1/chat/completions
AI_MODEL=...
```

تنظیمات ذخیره‌شده از داخل ربات می‌توانند بر defaults فایل env اولویت داشته باشند.

## تنظیمات Guard

مهم‌ترین متغیرها:

```env
AI_GUARD_CONFIDENCE_THRESHOLD=0.85
AI_GUARD_AI_CONFIDENCE_THRESHOLD=0.75
AI_GUARD_MAX_INPUT_CHARS=4000
AI_GUARD_MAX_OUTPUT_TOKENS=1800
AI_GUARD_MAX_CANDIDATES=8
AI_GUARD_CONTEXT_TTL_HOURS=24
AI_GUARD_CACHE_TTL_SECONDS=600
AI_GUARD_CACHE_SIZE=256
AI_GUARD_TIMEOUT_SECONDS=60
AI_GUARD_TOTAL_TIMEOUT_SECONDS=150
AI_GUARD_MAX_STAGES=12
AI_GUARD_MAX_REQUESTS=12
AI_GUARD_FAILURE_LIMIT=2
AI_GUARD_COOLDOWN_SECONDS=60
```

## اجرا

```powershell
python main.py
```

در اجرای سرور بهتر است session تلگرام از قبل آماده شده باشد. برای deployment می‌توان از Dockerfile موجود در ریشه پروژه استفاده کرد.

## تست‌ها

تست schema benchmark:

```powershell
pytest tests/test_guard_benchmark_schema.py -q
```

تست قراردادهای V4:

```powershell
pytest tests/test_guard_v4_contracts.py -q
```

اجرای بخشی از benchmark:

```powershell
python scripts/run_guard_benchmark.py --start 151 --limit 30
```

اجرای کل benchmark:

```powershell
python scripts/run_guard_benchmark.py
```

خروجی در فایل زیر نوشته می‌شود:

```text
guard_benchmark_report.json
```

Corpus فعلی benchmark شامل 189 کیس است. تعداد کیس‌ها به‌تنهایی تضمین کیفیت نیست؛ هر تغییر در prompt، classifier، rewrite، judge یا validator باید با regression benchmark و تست واقعی تلگرام بررسی شود.

## رفتار REVIEW

`REVIEW` باید آخرین مسیر باشد، نه مسیر پیش‌فرض. نمونه دلایل:

- ابهام واقعی
- تغییر معنی بعد از rewrite
- خروجی ناامن
- timeout یا خطای provider
- response نامعتبر
- تضاد بین مراحل
- تمام شدن budget

در پنل بررسی مدیر می‌توان متن را دید، بازنویسی AI درخواست کرد، ویرایش کرد، تأیید کرد یا رد کرد.

## ساختار مهم پروژه

```text
app/
  prompts/guardrails.txt
  services/
    ai_service.py
    ai_response.py
    output_validator.py
    moderation_service.py
    guard/
      pipeline.py
      contracts.py
  handlers/
    reviews.py

scripts/
  run_guard_benchmark.py

tests/
  data/guard_benchmark_v1.json
  test_guard_benchmark_schema.py
  test_guard_v4_contracts.py
```

## قواعد توسعه

- classifier نباید rewrite بنویسد.
- writer نباید تصمیم DROP بگیرد.
- Policy Judge نباید semantic fidelity را قضاوت کند.
- Meaning Judge نباید صرفاً به خاطر مؤدب نبودن متن fail کند.
- DROP حساس باید audit مستقل داشته باشد.
- خروجی AI همیشه باید با contract و validator بررسی شود.
- هیچ تغییر prompt نباید بدون regression test وارد master شود.
- پیام‌های واقعی را ابتدا روی Source/Destination آزمایشی تست کنید.

## نکات امنیتی

- `.env`، API key، BOT token و Telegram session را commit نکنید.
- پیام‌های ورودی را DATA در نظر بگیرید، نه دستور برای مدل.
- prompt injection باید از متن عادی/آموزشی درباره prompt injection تفکیک شود.
- در صورت خطای AI، پیام مشکوک نباید بدون بررسی منتشر شود.

## وضعیت نسخه

معماری فعلی: **Guard V4.1**

هدف اصلی این نسخه: کاهش false positive، حفظ معنی در rewrite و محدود کردن REVIEW به موارد واقعاً نیازمند تصمیم انسانی.
