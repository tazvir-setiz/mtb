# چک‌لیست اجرایی تحول و بهینه‌سازی گاردریل (Implementation Checklist & Handover Guide)
> **کاربرد:** این سند نقشه راه اجرایی گام‌به‌گام برای پیاده‌سازی تحول گارد است. هر فاز شامل تست‌های تاییدیه، دستور کامیت و وضعیت لحظه‌ای است.  
> **دستورالعمل تداوم کار (Handover Rule):** هر هوش مصنوعی یا توسعه‌دهنده‌ای که ادامه کار را دست می‌گیرد، باید اولین آیتم علامت‌نخورده (`[ ]`) را انجام دهد، تست‌ها را با `.\.venv\Scripts\pytest` اجرا کند، تغییرات را کامیت زده و وضعیت چک‌باکس را به `[x]` تغییر دهد.

---

## وضعیت کلی پروژه
* **تست‌های پایه:** ۴۴۵ تست پاس‌شده (`445 passed in 40s`)
* **فاز فعلی:** فاز ۱ (آماده‌سازی و اصلاح خطاهای زیرساختی)

---

## فاز ۱: اصلاح باگ‌های فوری و زیرساختی (Quick Wins & Bug Fixes)
- [ ] **گام ۱.۱: اصلاح حلقه نوتیفیکیشن ادمین در `app/handlers/reviews.py`**
  - **مسئله:** تکرار هشدار `Review notification failed admin=... detail=Chat not found` هر ۶۰ ثانیه به دلیل عدم شروع چت ادمین با ربات.
  - **اقدام:** اعمال تصاعد زمانی (Exponential Backoff: ۳۰۰s, ۱۸۰۰s, ۳۶۰۰s) برای ادمین‌های غیرقابل دسترس (`unreachable_admins`).
  - **فایل هدف:** `app/handlers/reviews.py`
  - **دستور تست:** `.\.venv\Scripts\pytest tests/test_reviews.py`
  - **پیام کامیت پیشنهادی:** `fix(reviews): apply exponential backoff for unreachable admin notifications`

- [ ] **گام ۱.۲: به‌روزرسانی تنظیمات تایم‌اوت و بودجه گارد در `app/guard_config.py`**
  - **مسئله:** معطلی بیش از حد (نزدیک به ۳۰ ثانیه برای یک پیام ۴۹ کاراکتری).
  - **اقدام:** بهینه‌سازی تایم‌اوت‌های پیش‌فرض و محدودسازی زمان اختصاص‌یافته به مراحل بازنویسی در پیام‌های کوتاه.
  - **فایل هدف:** `app/guard_config.py` و `app/services/guard/budget.py`
  - **دستور تست:** `.\.venv\Scripts\pytest tests/test_guard_pipeline.py`
  - **پیام کامیت پیشنهادی:** `perf(guard): optimize timeout budgets and stage latencies`

---

## فاز ۲: ارتقای پرامپت‌ها و رفع مشکل درک اسلنگ و لحن (Prompt Engineering & Slang Hardening)
- [ ] **گام ۲.۱: ارتقای پرامپت استخراج معنا (`decompose_meaning`) در `app/services/ai_service.py`**
  - **مسئله:** تبدیل اشتباه اسلنگ‌های عامیانه و کنایه (مثل «چسی جدید کتاب‌ها 😂») به گزاره‌های منفی قاطع.
  - **اقدام:** افزودن قوانین صریح درباره حفظ لحن طنز، عدم قضاوت‌سازی از اسلنگ‌های غیررسمی، و حفاظت از ایموجی‌های بیانگر لحن (`😂`, `😅`).
  - **فایل هدف:** `app/services/ai_service.py`
  - **دستور تست:** `.\.venv\Scripts\pytest tests/test_ai_policy.py tests/test_guard_pipeline.py`
  - **پیام کامیت پیشنهادی:** `fix(guard): protect humor tone, emojis, and slang context in meaning decomposition`

- [ ] **گام ۲.۲: بازنگری پرامپت بازنویسی (`generate_rewrite`) در `app/services/ai_service.py`**
  - **مسئله:** الگوی اجباریِ تبدیل واژگان تند به عبارت نامناسب «خیلی بد است» و تغییر ماهیت شوخی به ادعای حقوقی علیه محصولات.
  - **اقدام:** اعمال اصل ویرایش کمینه‌گرا (Minimal Edit) و بازنویسی متناسب با لحن (حفظ ساختار طنز و جایگزینی معادل‌های محترمانه مثل «پُز / ادای جدید» به جای «خیلی بد است»).
  - **فایل هدف:** `app/services/ai_service.py`
  - **دستور تست:** `.\.venv\Scripts\pytest tests/test_abuse_rewrite.py tests/test_review_rewriter.py`
  - **پیام کامیت پیشنهادی:** `fix(guard): enforce minimal edit and tone-preserving rephrasing in rewrite generator`

- [ ] **گام ۲.۳: افزودن گارد افترا و تخریب تجاری به خط‌مشی اصلی (`app/prompts/guardrails.txt`)**
  - **مسئله:** نبود بند شفاف درباره جلوگیری از تولید ادعاهای تخریبی یا افترا علیه برندها و محصولات.
  - **اقدام:** درج بند حفاظت از حقیقت گزاره‌ها (Defamation & Tone Inversion Prevention).
  - **فایل هدف:** `app/prompts/guardrails.txt`
  - **دستور تست:** `.\.venv\Scripts\pytest tests/test_prompt_consistency.py`
  - **پیام کامیت پیشنهادی:** `docs(prompts): add anti-defamation and register preservation guidelines`

---

## فاز ۳: ارتقای داوری معنایی و جلوگیری از خطای آبشاری (Ground-Truth Meaning Judge)
- [ ] **گام ۳.۱: بازطراحی داور معنایی (`judge_meaning`) در `app/services/ai_service.py`**
  - **مسئله:** داور معنایی به جای بررسی اصل پیام و لحن آن، فقط متن بازنویسی‌شده را با `protected_meaning` ناقص مقایسه می‌کرد.
  - **اقدام:** ارزیابی مستقل متن بازنویسی‌شده مستقیماً در برابر متن اولیه (`original`) با سنجش:
    1. آیا لحن از شوخی/طنز به جدی/قضاوتی تغییر کرده؟
    2. آیا ادعای کذبی نسبت داده شده؟
    3. آیا ایموجی‌های لحن حذف شده‌اند؟
  - **فایل هدف:** `app/services/ai_service.py` و `app/services/guard/pipeline.py`
  - **دستور تست:** `.\.venv\Scripts\pytest tests/test_guard_pipeline.py tests/test_guard_v4_contracts.py`
  - **پیام کامیت پیشنهادی:** `feat(guard): upgrade meaning judge with direct tone and hallucination verification`

- [ ] **گام ۳.۲: هدایت هوشمند به صف بررسی ادمین (`REVIEW`) در موارد عدم اطمینان لحن**
  - **مسئله:** سیستم وقتی نمی‌تواند یک کلمه اسلنگ یا شوخی را با اطمینان بازنویسی کند، نباید متن خودسرانه منتشر کند.
  - **اقدام:** اگر داور معنایی عدم تطابق لحن تشخیص داد، پیام بلافاصله با لیبل `REVIEW` به جدول `review_requests` برود تا ادمین تصمیم بگیرد.
  - **فایل هدف:** `app/services/guard/pipeline.py`
  - **دستور تست:** `.\.venv\Scripts\pytest tests/test_guard_pipeline.py`
  - **پیام کامیت پیشنهادی:** `feat(guard): route ambiguous slang and tone shifts to admin review`

---

## فاز ۴: افزودن تست‌های جامع رگرسیون (Regression & Benchmark Tests)
- [ ] **گام ۴.۱: افزودن تست‌های پیام ۲۹۰ و موارد مشابه اسلنگ فارسی به تست سوئیت**
  - **مسئله:** اطمینان از اینکه عبارت‌هایی نظیر «چسی جدید کتاب‌های کمک‌درسی 😂» دیگر هرگز به «خیلی بد هستند» بازنویسی نشوند.
  - **اقدام:** ایجاد فایل تستی اختصاصی با سناریوهای شوخی، کنایه، اسلنگ روزمره و ایموجی‌ها.
  - **فایل هدف:** `tests/test_guard_persian_slang_regression.py`
  - **دستور تست:** `.\.venv\Scripts\pytest tests/test_guard_persian_slang_regression.py`
  - **پیام کامیت پیشنهادی:** `test(guard): add regression suite for Persian slang and humor preservation`

- [ ] **گام ۴.۲: اجرای تست کامل کل پروژه و تایید نهایی**
  - **دستور اجرا:** `.\.venv\Scripts\pytest`
  - **شرط قبولی:** پاس شدن ۱۰۰٪ تمام تست‌ها بدون شکست (All Passing).

---

## راهنمای دستورات پرکاربرد برای ادامه کار (Cheatsheet)
* اجرای تست سوئیت:
  ```powershell
  .\.venv\Scripts\pytest
  ```
* اجرای یک فایل تستی مشخص:
  ```powershell
  .\.venv\Scripts\pytest tests/test_guard_pipeline.py -v
  ```
* ثبت کامیت استاندارد پس از هر گام:
  ```powershell
  git add <فایل‌های تغییر یافته>
  git commit -m "<پیام کامیت>"
  ```
