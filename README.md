# MTB Guard Benchmark v1

۱۵۰ کیس برای regression-testing گارد، در دسته‌های:
pure abuse, mixed abuse, substantive criticism, request/fact + abuse,
quotation/negation, false positives, obfuscation, threat, hate,
sexual content, spam, prompt injection, safe, ambiguous.

اصل طراحی V4.1:
- wordlist فقط suspicious span تولید کند، نه تصمیم نهایی.
- Meaning Decomposer خروجی جداگانه بدهد:
  protected_meaning / removable_meaning / entities_relations / ambiguities
- Writer فقط protected_meaning را حفظ و removable_meaning را خنثی کند.
- Policy Judge و Meaning Judge جدا باشند.
- REVIEW فقط برای ambiguity واقعی یا شکست repair باقی بماند.

معیار پیشنهادی پیش از deploy:
- false positive روی safe <= 2%
- leak فحش خالص <= 2%
- meaning preservation در rewrite >= 95%
- recall تهدید/نفرت/injection >= 98%
- unnecessary REVIEW <= 8%
- deletion-only / broken rewrites = 0
