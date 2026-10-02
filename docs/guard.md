# راهنمای Guard V4.1 — معماری، Ruleها و روند تغییر

این فایل مرجع اصلی توسعه و نگهداری Guard در پروژه MTB است.

هدف Guard این است که قبل از انتشار پیام، بین چهار حالت اصلی تصمیم بگیرد:

- پیام بدون تغییر قابل انتشار است.
- پیام فقط به پاک‌سازی محلی نیاز دارد.
- پیام دارای بخش نامناسب است ولی معنی سالم آن قابل حفظ و بازنویسی است.
- پیام باید حذف شود یا برای تصمیم مدیر به REVIEW برود.

اصل مهم پروژه این است که **وجود یک کلمه مشکوک به‌تنهایی تصمیم نهایی نیست**. تصمیم باید بر اساس معنی پیام، زمینه، قابلیت حفظ محتوای سالم و قراردادهای هر مرحله گرفته شود.

---

## 1. مسیر کلی پردازش

مسیر اصلی پیام:

```text
Telegram message
      ↓
message_sender
      ↓
moderation_service.moderate
      ↓
Normalization + local rules + context + cache
      ↓
GuardPipeline
      ↓
Analyze
      ↓
Reassess (only when needed)
      ↓
Independent DROP audit
      ↓
Meaning decomposition
      ↓
Rewrite generation
      ↓
Policy Judge
      ↓
Meaning Judge
      ↓
Repair (one attempt when repairable)
      ↓
Final Policy Judge + Final Meaning Judge
      ↓
PUBLISH / DROP / REVIEW
```

انتقال دستی و Auto-Forward باید از همین مسیر Guard استفاده کنند تا دو رفتار متفاوت برای یک پیام ایجاد نشود.

---

## 2. فایل‌های مهم Guard

### سیاست اصلی

```text
app/prompts/guardrails.txt
```

این فایل قوانین معنایی اصلی را به مدل می‌دهد؛ از جمله تعریف labelها، نحوه تشخیص abuse، threat، hate، spam، injection، قواعد احترام مذهبی و سیاست‌های سفارشی پروژه.

اگر می‌خواهید **معنی یک Rule یا رفتار طبقه‌بندی مدل** تغییر کند، معمولاً اولین فایل برای بررسی همین فایل است.

---

### هماهنگ‌کننده اصلی

```text
app/services/moderation_service.py
```

وظایف اصلی:

- بارگذاری تنظیمات AI و Guard
- کنترل فعال بودن AI
- محدودیت طول ورودی
- normalization
- context
- cache
- اجرای Rule Engine محلی
- تصمیم برای ورود به AI pipeline
- ذخیره context
- ثبت metrics و log

تغییر یک Rule محتوایی معمولاً نباید با اضافه کردن ifهای پراکنده در این فایل انجام شود.

---

### Pipeline چندمرحله‌ای

```text
app/services/guard/pipeline.py
```

این فایل ترتیب مراحل AI را کنترل می‌کند.

نمونه مراحل:

```text
analyze
reassess
drop_audit
meaning decomposition
rewrite
policy judge
meaning judge
repair
final judges
```

اگر قرار است **ترتیب مراحل، شرط ورود به مرحله، تعداد auditها یا رفتار fallback** تغییر کند، این فایل محل اصلی تغییر است.

---

### قرارداد خروجی مراحل

```text
app/services/guard/contracts.py
```

ساختارهای فعلی:

- `MeaningDecomposition`
- `RewriteDraft`
- `PolicyVerdict`
- `MeaningVerdict`

Validatorهای این فایل تضمین می‌کنند مدل هر متن آزاد یا JSON ناقصی را وارد سیستم نکند.

هر زمان schema خروجی یک مرحله تغییر می‌کند، قرارداد و تست آن نیز باید همزمان تغییر کنند.

---

### مدل‌ها و Labelها

فایل‌های مرتبط:

```text
app/services/guard_models.py
app/services/guard/
```

قبل از اضافه کردن label جدید بررسی کنید آیا واقعاً label جدید لازم است یا همان Rule را می‌توان با labelهای موجود مدل کرد.

اضافه کردن label جدید معمولاً فقط تغییر enum نیست؛ mapping، parser، pipeline، review flow، benchmark و تست‌ها نیز ممکن است تحت تأثیر قرار بگیرند.

---

### Rule Engine محلی

```text
app/services/rule_guard.py
```

Rule Engine برای تصمیم‌های کم‌هزینه و واضح است.

قاعده مهم:

> Local Rule نباید از یک substring یا کلمه مبهم نتیجه سنگین مثل DROP بگیرد.

Ruleهای محلی باید محافظه‌کارانه باشند. موارد معنایی، دوپهلو، نقل‌قول، گزارش، کنایه، متن آموزشی یا مواردی که نیاز به فهم context دارند بهتر است به AI سپرده شوند.

---

### Normalizer و Sanitizer

```text
app/services/text_normalizer.py
app/services/text_sanitizer.py
```

Normalizer برای تشخیص و ساخت variant است.

Sanitizer برای آماده‌سازی متن قابل انتشار، حذف لینک/username یا کنترل خروجی نهایی استفاده می‌شود.

Normalization نباید باعث شود نسخه decode شده یا تغییرشکل‌یافته پیام به عنوان متن نهایی منتشر شود.

---

### Runtime و Metrics

```text
app/services/guard_runtime.py
```

Metrics برای فهم مسیر واقعی پیام‌ها استفاده می‌شوند.

نمونه شمارنده‌های مهم:

- `total_messages`
- `rule_decisions`
- `ai_decisions`
- `primary_model_calls`
- `fallback_model_calls`
- `model_escalations`
- `grounding_attempts` / `grounding_candidate` / `grounding_no_match`
- `ai_calls`
- `cache_hits`
- `blocked_messages`
- `review_messages`
- `automatic_rechecks`
- `drop_audits`
- `repair_attempts`
- `verified_messages`

هنگام تغییر معماری Guard فقط pass شدن تست کافی نیست؛ تغییر رفتار metrics نیز باید بررسی شود.

---

## 3. Labelها و رفتار مورد انتظار

| Label | رفتار |
|---|---|
| `OK` | انتشار بدون تغییر معنایی |
| `SANITIZE` | انتشار پس از پاک‌سازی لینک/username و موارد محلی |
| `REWRITE` | حفظ معنی سالم و بازنویسی بخش نامناسب |
| `REVIEW` | ارجاع به مدیر به دلیل ابهام یا شکست مرحله‌ای |
| `ABUSE` | توهین مستقیم بدون محتوای مستقل قابل حفظ |
| `HATE` | حمله یا تحقیر تعمیم‌یافته علیه گروه |
| `THREAT` | تهدید یا ارعاب معتبر |
| `PORN` | محتوای جنسی صریح طبق سیاست پروژه |
| `SPAM` | اسپم، کلاهبرداری یا تبلیغ ممنوع |
| `INJECTION` | تلاش برای کنترل یا دور زدن Guard |
| `POLITICAL` | advocacy سیاسی صریح که طبق policy پروژه نیازمند REVIEW است |

نکته: موضوع سیاسی به‌تنهایی به معنی `POLITICAL` نیست. خبر، گزارش، نقل‌قول منتسب، بحث تاریخی یا توصیف خنثی نباید فقط به خاطر نام کشور، مسئول یا موضوع سیاسی REVIEW شود.

---

## 4. تفاوت ABUSE و REWRITE

یکی از مهم‌ترین Ruleهای Guard همین تفاوت است.

### ABUSE

وقتی پیام عملاً فقط حمله یا توهین است و معنی سالم مستقلی برای حفظ وجود ندارد.

مثال:

```text
کسکش
```

در این حالت:

```text
ABUSE → DROP
```

برای DROP از نوع ABUSE، classifier باید `has_substance=false` داشته باشد و تصمیم حساس با audit مستقل بررسی می‌شود.

---

### REWRITE

وقتی پیام بخش نامناسب دارد اما معنی سالم مستقلی نیز وجود دارد.

مثال:

```text
سلام کله کیری
```

معنی سالم «سلام کردن» قابل حفظ است.

مسیر مورد انتظار:

```text
REWRITE
→ Meaning Decomposition
→ Rewrite
→ Policy Judge
→ Meaning Judge
→ Publish
```

مثال دیگر:

```text
قیافه‌ات خیلی زشته، این عکس را عوض کن
```

صرف حذف تمام جمله ممکن است معنی درخواست را از بین ببرد. Rewrite باید محتوای قابل حفظ را نگه دارد.

---

## 5. Meaning Decomposition

قبل از Rewrite، معنی پیام به چهار بخش تقسیم می‌شود:

```json
{
  "protected_meaning": [],
  "removable_meaning": [],
  "entities_relations": [],
  "ambiguities": []
}
```

### protected_meaning

اطلاعات، درخواست، ادعا یا رابطه‌ای که باید در نسخه نهایی باقی بماند.

### removable_meaning

بخش‌هایی که طبق policy باید حذف یا خنثی شوند.

### entities_relations

افراد، اشیا، نسبت‌ها و رابطه‌های مهم متن.

### ambiguities

ابهام‌هایی که مدل نمی‌تواند با اطمینان حل کند.

اگر `protected_meaning` وجود نداشته باشد، سیستم نباید به زور یک Rewrite تولید و منتشر کند.

---

## 6. Rewrite در V4.1

Classifier اجازه ندارد متن جایگزین بنویسد.

مسئولیت‌ها جدا هستند:

```text
Classifier → تشخیص
Meaning Decomposer → مشخص کردن معنی
Rewrite Generator → ساخت متن
Policy Judge → بررسی policy
Meaning Judge → بررسی حفظ معنی
```

این جداسازی برای جلوگیری از این مشکل است که همان مدل هم متن را بسازد و هم بدون بررسی مستقل، متن خودش را تأیید کند.

---

## 7. Policy Judge و Meaning Judge

### Policy Judge

فقط بررسی می‌کند آیا متن نهایی قابل انتشار است یا خیر.

نباید وظیفه اصلی آن بررسی fidelity معنایی باشد.

### Meaning Judge

بررسی می‌کند:

- protected meaning حذف نشده باشد.
- polarity ادعا عوض نشده باشد.
- entity یا target تغییر نکرده باشد.
- ادعای جدید ساخته نشده باشد.
- معنی مهم بیش از حد تضعیف یا تقویت نشده باشد.

نباید صرفاً به دلیل رسمی یا مؤدب نبودن متن fail کند.

---

## 8. Repair

اگر Rewrite اولیه fail شود و مشکل قابل اصلاح باشد:

```text
original
+
draft
+
judge issues
        ↓
repair
        ↓
Policy Judge
+
Meaning Judge
```

در V4.1 repair محدود است و نباید به loop نامحدود تبدیل شود.

اگر خروجی repair هنوز policy یا meaning را پاس نکند:

```text
REVIEW
```

---

## 9. DROP Audit

DROP تصمیم پرریسکی است.

به همین دلیل وقتی classifier تصمیم `DROP` می‌دهد، یک بررسی مستقل دیگر اجرا می‌شود.

اگر دو مرحله درباره label یا اصل DROP توافق نداشته باشند، سیستم نباید با اطمینان کاذب پیام را حذف کند.

مسیر محافظه‌کارانه معمولاً:

```text
conflict → REVIEW
```

برای ABUSE، وجود `has_substance` اهمیت ویژه دارد. اگر بخشی از پیام قابل حفظ باشد، pipeline باید امکان Rewrite را بررسی کند.

---

## 10. REVIEW چه زمانی استفاده می‌شود؟

REVIEW آخرین مسیر است، نه مسیر پیش‌فرض.

موارد معمول:

- ابهام واقعی
- confidence ناکافی
- conflict بین stages
- تغییر معنی بعد از rewrite
- unsafe output
- invalid schema
- timeout
- provider error
- input بیش از حد بلند
- تمام شدن stage/request budget
- عدم وجود protected meaning در مسیری که rewrite انتظار می‌رود

هدف تغییرات آینده باید کاهش REVIEWهای غیرضروری باشد، نه حذف REVIEW به هر قیمت.

---

# بخش دوم — روش صحیح تغییر Guard Rule

## 11. قبل از تغییر Rule

قبل از تغییر کد، مشکل را به یک مثال قابل تست تبدیل کنید.

به جای:

```text
گارد فحش را بد تشخیص می‌دهد
```

بنویسید:

```text
Input:
"سلام فلان فحش"

Expected:
SEND / REWRITE

Current:
DROP / ABUSE
```

یا:

```text
Input:
"فلان توهین خالص"

Expected:
DROP / ABUSE

Current:
SEND / OK
```

همیشه این چهار مورد را ثبت کنید:

1. input
2. current action/label
3. expected action/label
4. دلیل مورد انتظار

---

## 12. تشخیص محل صحیح تغییر

### حالت A — Rule فقط معنایی است

مثال:

- تفاوت نقد با توهین
- نقل‌قول
- گزارش درباره توهین
- تشخیص insult همراه با محتوای قابل حفظ

اول بررسی کنید:

```text
app/prompts/guardrails.txt
```

در بسیاری از موارد نباید pipeline را تغییر دهید.

---

### حالت B — Rule قطعی و محلی است

مثال:

- پاک‌سازی ساده
- pattern کاملاً مشخص
- تصمیمی که به context نیاز ندارد

بررسی کنید:

```text
app/services/rule_guard.py
```

Rule محلی باید false positive بسیار کمی داشته باشد.

---

### حالت C — مشکل از ترتیب مراحل است

مثال:

- DROP بدون audit منتشر می‌شود.
- Rewrite بدون judge نهایی پذیرفته می‌شود.
- REVIEW قبل از reassess ایجاد می‌شود.

محل بررسی:

```text
app/services/guard/pipeline.py
```

---

### حالت D — خروجی مدل معتبر نیست

مثال:

- فیلدی گاهی string و گاهی array می‌شود.
- judge با `passed=true` هم issue برمی‌گرداند.
- مدل JSON ناقص تولید می‌کند.

محل بررسی:

```text
app/services/guard/contracts.py
app/services/output_validator.py
app/services/ai_response.py
```

Validator را برای pass شدن یک پاسخ خراب شل نکنید. ابتدا مشخص کنید آیا schema واقعاً باید تغییر کند یا مدل باید به قرارداد فعلی برگردد.

---

### حالت E — مشکل از context/cache است

مثال:

- نتیجه پیام قبلی روی پیام جدید اثر اشتباه دارد.
- تغییر policy اعمال نشده ولی cache قدیمی استفاده شده.
- alias اشتباه ذخیره شده.

بررسی کنید:

```text
app/services/context_manager.py
app/services/guard_runtime.py
app/services/moderation_service.py
```

Cache key باید تغییرات مؤثر بر تصمیم را در fingerprint داشته باشد.

---

## 13. روش پیشنهادی تغییر یک Rule

روند استاندارد:

```text
1. Reproduce
2. Add benchmark case
3. Add focused unit/contract test if needed
4. Make the smallest rule change
5. Run focused tests
6. Run nearby benchmark cases
7. Run full benchmark
8. Inspect failures
9. Check Telegram behavior
10. Deploy to test destination
11. Inspect logs/metrics
12. Merge
```

---

## 14. مرحله اول: Reproduce

اول مطمئن شوید مشکل در نسخه فعلی قابل تکرار است.

برای benchmark:

```powershell
python scripts/run_guard_benchmark.py --start 1 --limit 20
```

اگر case جدید هنوز داخل corpus نیست، ابتدا آن را به benchmark اضافه کنید.

---

## 15. اضافه کردن Benchmark Case

فایل اصلی:

```text
tests/data/guard_benchmark_v1.json
```

Case باید حداقل مشخص کند:

```json
{
  "id": "case_xxx",
  "category": "safe_plus_abuse",
  "text": "متن نمونه",
  "expected_action": "SEND",
  "expected_label": "REWRITE"
}
```

برای پیام نامناسب خالص:

```json
{
  "id": "case_xxx",
  "category": "pure_abuse",
  "text": "متن نمونه",
  "expected_action": "DROP",
  "expected_label": "ABUSE"
}
```

Expected را بر اساس رفتار موردنظر پروژه بنویسید، نه بر اساس خروجی فعلی مدل.

---

## 16. تست Contract

برای تغییر قراردادهای V4:

```text
tests/test_guard_v4_contracts.py
```

اجرا:

```powershell
pytest tests/test_guard_v4_contracts.py -q
```

اگر schema تغییر کرده ولی این تست‌ها بدون تغییر پاس می‌شوند، احتمالاً coverage کافی برای قرارداد جدید ندارید.

---

## 17. تست schema benchmark

```powershell
pytest tests/test_guard_benchmark_schema.py -q
```

قبل از benchmark واقعی این تست را اجرا کنید تا خطاهای ساختاری corpus جدا از کیفیت مدل مشخص شوند.

---

## 18. اجرای بخشی از Benchmark

برای توسعه سریع:

```powershell
python scripts/run_guard_benchmark.py --start 151 --limit 30
```

اگر تغییر مربوط به چند category خاص است، ابتدا بخش نزدیک به همان caseها را اجرا کنید.

---

## 19. اجرای کامل Benchmark

قبل از merge:

```powershell
python scripts/run_guard_benchmark.py
```

گزارش در:

```text
guard_benchmark_report.json
```

فقط pass rate را نگاه نکنید.

بررسی کنید:

- چه caseهایی fail شده‌اند.
- fail جدید regression است یا expected قدیمی اشتباه است.
- تعداد DROP ناگهان زیاد نشده باشد.
- REVIEW بی‌دلیل افزایش پیدا نکرده باشد.
- REWRITE به OK تبدیل نشده باشد وقتی بخش نامناسب هنوز وجود دارد.
- معنی خروجی rewrite واقعاً حفظ شده باشد.

---

## 20. تست Regression

هر باگی که اصلاح می‌شود باید تا حد ممکن تبدیل به regression case شود.

اصل:

> باگی که فقط با Prompt اصلاح شده ولی test ندارد، ممکن است در تغییر Prompt بعدی دوباره برگردد.

برای هر bug مهم یکی از این‌ها لازم است:

- benchmark case
- unit test
- contract test

گاهی هر سه لازم هستند.

---

# بخش سوم — تغییر Prompt

## 21. چه زمانی Prompt را تغییر دهیم؟

Prompt مناسب است وقتی مشکل مربوط به **برداشت معنایی مدل** است.

مثال:

- مدل quotation را به اشتباه abuse نویسنده می‌داند.
- مدل به علت وجود یک keyword کل پیام را DROP می‌کند.
- مدل safe meaning را تشخیص نمی‌دهد.
- مدل distinction بین abuse و threat را اشتباه می‌گیرد.

---

## 22. چگونه Prompt را تغییر دهیم؟

Rule جدید باید:

- کوتاه باشد.
- دقیق باشد.
- exception مشخص داشته باشد.
- با Ruleهای قبلی تضاد ایجاد نکند.
- تا جای ممکن مثال مرزی داشته باشد.
- از keyword-only classification جلوگیری کند.

بد:

```text
هر پیام دارای X را حذف کن.
```

بهتر:

```text
وجود X فقط یک signal است.
معنی را در context بررسی کن.
quotation/reporting/negation را violation نویسنده حساب نکن.
اگر independent safe meaning وجود دارد REWRITE را بررسی کن.
```

---

## 23. از زیاد کردن مثال‌ها بدون کنترل خودداری کنید

Prompt بزرگ‌تر همیشه Prompt بهتر نیست.

افزایش بی‌رویه مثال‌ها ممکن است:

- latency را بالا ببرد.
- token مصرف کند.
- ruleهای قبلی را تضعیف کند.
- overfitting ایجاد کند.
- رفتار مدل روی caseهای دیگر را تغییر دهد.

پس بعد از هر تغییر Prompt حتماً full benchmark لازم است.

---

# بخش چهارم — تغییر Pipeline

## 24. Pipeline را فقط وقتی تغییر دهید که Prompt کافی نیست

تغییر Pipeline پرریسک‌تر از Prompt است.

نمونه تغییرات منطقی:

- اضافه کردن audit مستقل
- جدا کردن classification از rewrite
- اضافه کردن judge مستقل
- اضافه کردن repair محدود
- تغییر fallback از DROP به REVIEW هنگام conflict

نمونه تغییرات نامناسب:

- اضافه کردن if برای یک جمله خاص
- bypass کردن judge برای افزایش pass rate
- تبدیل تمام errorها به OK
- حذف REVIEW فقط برای کمتر شدن صف مدیر

---

## 25. Budget مراحل

Guard دارای محدودیت مرحله و درخواست است.

متغیرهای مهم:

```env
AI_GUARD_MAX_STAGES=12
AI_GUARD_MAX_REQUESTS=12
AI_GUARD_TIMEOUT_SECONDS=60
AI_GUARD_TOTAL_TIMEOUT_SECONDS=150
```

اضافه کردن stage جدید بدون توجه به budget می‌تواند پیام سالم را به REVIEW ناشی از timeout یا budget exhaustion ببرد.

---

# بخش پنجم — تنظیمات

## 26. تنظیمات اصلی Guard

مقادیر مرجع فعلی پروژه:

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

توجه: قبل از تغییر defaultها، مقدار واقعی environment و تنظیمات ذخیره‌شده داخل ربات را بررسی کنید؛ تنظیمات runtime می‌توانند با env متفاوت باشند.

---

## 27. Confidence

کم کردن confidence threshold ممکن است REVIEW را کاهش دهد ولی false positive/false negative را افزایش دهد.

بالا بردن آن نیز ممکن است REVIEW را زیاد کند.

Confidence tuning باید با corpus واقعی انجام شود، نه با چند مثال موفق.

---

## 28. Cache

فقط تصمیم‌های قابل انتشار باید cache شوند.

تصمیم‌های زیر نباید کورکورانه cache شوند:

- error
- REVIEW
- DROP حساس

بعد از تغییر policy، model، endpoint یا تنظیمات مهم، fingerprint باید باعث cache miss مناسب شود.

---

# بخش ششم — Context

## 29. Context چه کاری انجام می‌دهد؟

Context برای نگهداری محدود اطلاعات مرتبط با منبع استفاده می‌شود.

نمونه:

- topic
- entity
- alias صریح

Context باید محدود، TTLدار و محافظه‌کارانه باشد.

نباید یک برداشت حدسی مدل را به حقیقت دائمی برای پیام‌های بعدی تبدیل کند.

---

## 30. Alias

Alias باید از تعریف صریح متن استخراج شود.

مثال قابل قبول:

```text
دیوار یعنی حکومت
```

نباید صرفاً از یک استعاره مبهم، alias دائمی ساخته شود.

---

# بخش هفتم — Review Flow

## 31. REVIEW به معنی تأیید مدیر نیست

وقتی پیام وارد REVIEW شد:

- خودکار منتشر نمی‌شود.
- مدیر می‌تواند بررسی کند.
- می‌تواند دوباره AI را اجرا کند.
- می‌تواند متن را ویرایش کند.
- می‌تواند تأیید یا رد کند.

Retry انتقال نباید معادل approve در نظر گرفته شود.

---

## 32. Recheck با AI

Recheck فقط یک draft/decision جدید می‌سازد.

بعد از ارجاع پیام به مدیر، خروجی AI نباید بدون تصمیم مدیر خودکار منتشر شود.

این تفکیک برای جلوگیری از bypass شدن review queue مهم است.

---

# بخش هشتم — Logging و Debug

## 33. Log اصلی Guard

تصمیم Guard شامل اطلاعاتی مانند موارد زیر است:

```text
chat_id
message_id
source
label
confidence
cached
elapsed
ai_call_ratio
action
```

در Debug ابتدا به این‌ها نگاه کنید:

1. `source=RULE` یا `source=AI`
2. label
3. action
4. reason
5. stage مربوط
6. timeout یا invalid schema
7. cache hit

---

## 34. Reasonهای مهم

نمونه reasonها:

- `input_too_long`
- `unsafe_output`
- `ambiguous_meaning`
- `no_protected_meaning`
- `meaning_changed`
- `rewrite_failed`
- `conflicting_drop_decisions`
- `invalid_meaning`
- `invalid_rewrite`
- `invalid_policy_verdict`
- `invalid_meaning_verdict`

اگر تعداد یک reason ناگهان زیاد شد، قبل از تغییر threshold علت stage مربوط را بررسی کنید.

---

# بخش نهم — سناریوهای نمونه تغییر Rule

## 35. مثال: Safe + Abuse به اشتباه DROP می‌شود

مشکل:

```text
"سلام ...[توهین]"
Current: DROP / ABUSE
Expected: SEND / REWRITE
```

روند:

1. benchmark case اضافه کنید.
2. بررسی کنید analyzer چرا `has_substance=false` داده است.
3. Rule مربوط به independent safe meaning در `guardrails.txt` را اصلاح کنید.
4. اگر DROP audit نیز همین اشتباه را دارد، prompt audit را بررسی کنید.
5. pipeline را فقط در صورت مشکل ساختاری تغییر دهید.
6. focused benchmark اجرا کنید.
7. full benchmark اجرا کنید.

---

## 36. مثال: توهین خالص به اشتباه OK می‌شود

```text
Current: SEND / OK
Expected: DROP / ABUSE
```

بررسی:

- آیا normalization متن را خراب کرده؟
- آیا local rule confidence اشتباه دارد؟
- آیا classifier evidence درست می‌دهد؟
- آیا `ABUSE` دارای `has_substance=false` است؟
- آیا drop audit تصمیم را برگردانده؟
- آیا disabled sensitivity باعث خاموش شدن category شده؟

---

## 37. مثال: Rewrite معنی را عوض می‌کند

مشکل classifier نیست.

بررسی کنید:

```text
Meaning Decomposition
Rewrite Prompt
Meaning Judge
Repair
```

Meaning Judge باید regression مورد نظر را بگیرد.

اگر judge متن غلط را pass می‌کند، فقط Writer را دستکاری نکنید؛ guardrail دفاعی judge نیز باید اصلاح شود.

---

## 38. مثال: همه چیز REVIEW می‌شود

قبل از پایین آوردن confidence بررسی کنید:

- invalid JSON
- max output token
- timeout
- provider error
- schema mismatch
- policy/meaning judge conflict
- max stages
- max requests
- custom policy
- model compatibility

REVIEW زیاد همیشه به معنی threshold بالا نیست.

---

# بخش دهم — چیزهایی که نباید انجام دهیم

## 39. Anti-patternها

این کارها ممنوع یا بسیار پرریسک هستند:

- keyword = DROP بدون context
- انتشار خروجی Rewrite بدون judge
- bypass کردن validator
- قبول JSON ناقص برای سبز شدن تست
- تبدیل error به OK
- حذف REVIEW برای بهتر شدن pass rate ظاهری
- تغییر چند Rule بزرگ در یک commit بدون benchmark
- تغییر expected benchmark فقط برای pass شدن نسخه جدید
- cache کردن تصمیم‌های خطادار
- اعتماد به متن ورودی به عنوان instruction
- ثبت API key یا prompt محرمانه در log
- merge کردن تغییر Prompt بدون regression test

---

# بخش یازدهم — چک‌لیست قبل از Commit

## 40. چک‌لیست توسعه

- [ ] مشکل با input مشخص reproduce شد.
- [ ] expected action/label مشخص است.
- [ ] benchmark case اضافه یا به‌روزرسانی شد.
- [ ] تغییر در کوچک‌ترین لایه مناسب انجام شد.
- [ ] Rule محلی به keyword matching خطرناک تبدیل نشده است.
- [ ] classifier مسئول Rewrite نشده است.
- [ ] DROP حساس همچنان audit دارد.
- [ ] Rewrite همچنان Policy Judge و Meaning Judge دارد.
- [ ] validator شل نشده است.
- [ ] focused tests پاس هستند.
- [ ] focused benchmark بررسی شده است.
- [ ] full benchmark اجرا شده است.
- [ ] regressionهای جدید بررسی شده‌اند.
- [ ] log/reason مسیر جدید قابل فهم است.
- [ ] README/docs در صورت تغییر معماری به‌روز شده‌اند.

---

# بخش دوازدهم — دستورات تست پیشنهادی

## 41. Contract tests

```powershell
pytest tests/test_guard_v4_contracts.py -q
```

## 42. Benchmark schema

```powershell
pytest tests/test_guard_benchmark_schema.py -q
```

## 43. بخشی از benchmark

```powershell
python scripts/run_guard_benchmark.py --start 151 --limit 30
```

## 44. کل benchmark

```powershell
python scripts/run_guard_benchmark.py
```

---

# بخش سیزدهم — روند پیشنهادی Git

برای تغییر Rule بهتر است commitها کوچک و قابل برگشت باشند.

مثال:

```text
test(guard): add regression cases for safe-plus-abuse
fix(guard): preserve substantive meaning in abuse classification
docs(guard): document guard rule change workflow
```

اگر Prompt و Pipeline هر دو تغییر می‌کنند، ترجیحاً تا جای ممکن در commitهای منطقی جدا باشند تا regression قابل ردیابی باشد.

---

# بخش چهاردهم — تست قبل از Deploy واقعی

بعد از تست خودکار:

1. مقصد آزمایشی انتخاب کنید.
2. Auto-Forward را روی محیط کنترل‌شده تست کنید.
3. حداقل یک پیام `OK` بفرستید.
4. یک پیام `SANITIZE` بفرستید.
5. یک پیام `REWRITE` بفرستید.
6. یک `ABUSE/DROP` تست کنید.
7. یک case مبهم برای `REVIEW` تست کنید.
8. متن rewrite شده را دستی با اصل مقایسه کنید.
9. Runtime log را بررسی کنید.
10. سپس روی مقصد واقعی فعال کنید.

---

# بخش پانزدهم — اصول طراحی Guard

Guard باید این اصول را حفظ کند:

### 1. Meaning over keyword

معنی از keyword مهم‌تر است.

### 2. Preserve useful content

وجود توهین به معنی حذف تمام اطلاعات سالم پیام نیست.

### 3. Separate responsibilities

Classifier، Writer، Policy Judge و Meaning Judge وظیفه یکسان ندارند.

### 4. Independent verification

خروجی مولد باید توسط مرحله مستقل بررسی شود.

### 5. Conservative destructive actions

DROP از PUBLISH پرریسک‌تر است و باید evidence و audit مناسب داشته باشد.

### 6. REVIEW is a safety valve

REVIEW برای uncertainty واقعی است، نه جایگزین classifier.

### 7. Tests define regressions

هر bug مهم باید به test یا benchmark تبدیل شود.

### 8. Small changes

Ruleها را تا جای ممکن با تغییر کوچک و قابل اندازه‌گیری اصلاح کنید.

---

## وضعیت فعلی

معماری مستندشده در این فایل:

```text
Guard V4.1
```

مرجع خلاصه پروژه:

```text
README.md
```

مرجع policy:

```text
app/prompts/guardrails.txt
```

مرجع flow:

```text
app/services/guard/pipeline.py
```

مرجع قراردادها:

```text
app/services/guard/contracts.py
```

مرجع benchmark:

```text
tests/data/guard_benchmark_v1.json
scripts/run_guard_benchmark.py
```

هر تغییری که رفتار Guard را عوض می‌کند باید با این سه چیز همراه باشد:

```text
Rule change
+ Regression test
+ Benchmark verification
```

## Model routing and news grounding

The default primary model is `gpt-6-luna`; the default hard-case model is
`gpt-5.6-luna`. Environment values provide deployment defaults. A saved
database value overrides its corresponding environment value, preserving the
existing bot settings behavior. Old databases need no migration: absent keys
use deployment defaults. Existing `ai_model` values remain authoritative.

The primary handles ordinary stages. At most one fallback call is permitted
per moderation request. It can resolve an uncertain REVIEW, a retryable
provider/output failure, or a failed rewrite verification. Authentication,
permission, rate-limit, bad-request, and open-circuit failures do not trigger
fallback. The same stage, request, timeout and total-duration limits apply;
fallback does not skip schema, policy, meaning, sanitization or verification.

News search runs only when classification supplies a short grounding query for
a concrete, unresolved public factual/news claim. The query uses three to ten
words from the original after removing URLs, handles and contact details.
Search is bounded to five results, 8 seconds and 256 KB per response. Google
News RSS serves only as discovery; evidence requires an allowed HTTPS publisher
URL and an extracted article title and timezone-aware publication date.
Redirect destinations are checked at every hop and only public DNS addresses
are accepted. Stale or undated results are ignored; one matching article is
provided to the model. Conflicting matching reports produce REVIEW. Retrieval
does not establish truth or resolve actor identity by itself. External page
text is untrusted data. The model must preserve attribution and uncertainty
and pass the ordinary judges. A source name is omitted unless needed to avoid
overstating a claim. Grounded outcomes bypass the publish cache and conversation
context, so time-sensitive evidence is fetched again.

Configuration (database values override ENV):

- `AI_MODEL` / `ai_model`: primary; default `gpt-6-luna`.
- `AI_FALLBACK_MODEL` / `ai_fallback_model`: one-call fallback; default `gpt-5.6-luna`.
- `NEWS_GROUNDING_ENABLED` / `news_grounding_enabled`: on-demand lookup switch; default `true`.
- `NEWS_ALLOWED_DOMAINS` / `news_allowed_domains`: comma-separated exact HTTPS publisher hosts; default domains appear in `.env.example`. Invalid stored values fail closed.

Set `NEWS_GROUNDING_ENABLED=false` to disable lookup. Run `python -m pytest -q`
for unit and mocked transport coverage. Run
`python scripts/run_guard_benchmark.py --start 151 --limit 43 --output benchmark-151-193.json`
then `python scripts/run_guard_benchmark.py --start 1 --limit 193 --output benchmark-1-193.json`
for the required regression ranges. Benchmark execution uses the configured
provider, requires valid AI settings and can incur provider cost.
