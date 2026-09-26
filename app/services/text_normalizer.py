import base64
import binascii
import codecs
import re
import unicodedata
from dataclasses import dataclass
from html import unescape
from urllib.parse import unquote

TRANSLATION = str.maketrans("يكۀة۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "یکهه01234567890123456789")


@dataclass(frozen=True)
class NormalizedText:
    original: str
    normalized: str
    candidates: tuple[str, ...]
    flags: frozenset[str]


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).translate(TRANSLATION).casefold()
    text = "".join(
        c for c in text if c != "ـ" and unicodedata.category(c) not in {"Cf", "Mn", "Me"}
    )
    return " ".join(text.split())


def normalize_text(text: str, max_candidates: int = 8) -> NormalizedText:
    base = normalize(text)
    flags = set()
    if any(unicodedata.category(c) == "Cf" and c != "\u200c" for c in text):
        flags.add("invisible")
    if re.search(r"(.)\1{3,}", base):
        flags.add("repeated")
    if re.search(r"(?:\b\w\b[\W_]+){2,}", base):
        flags.add("separated")
    candidates = [base]
    encoded = []
    if re.search(r"%[0-9a-fA-F]{2}|&#(?:x[0-9a-fA-F]+|\d+);|\\u[0-9a-fA-F]{4}", text):
        flags.add("encoded")
        decoded = unescape(unquote(text))
        decoded = re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m[1], 16)), decoded)
        encoded.append(decoded)
    for token in re.findall(r"(?<!\w)[A-Za-z0-9+/=]{16,}(?!\w)", text)[:2]:
        try:
            decoded = base64.b64decode(token, validate=True).decode("utf-8")
            if decoded and all(c.isprintable() or c.isspace() for c in decoded):
                flags.add("encoded")
                encoded.append(decoded)
        except (ValueError, UnicodeError, binascii.Error):
            pass
    for token in re.findall(r"\b(?:[0-9a-fA-F]{2}){8,}\b", text)[:2]:
        try:
            encoded.append(bytes.fromhex(token).decode("utf-8"))
            flags.add("encoded")
        except (ValueError, UnicodeError):
            pass
    candidates.extend(normalize(value) for value in encoded)
    candidates.extend(
        [
            re.sub(r"[\W_]+", "", base),
            re.sub(r"(.)\1{2,}", r"\1", base),
            " ".join(word[::-1] for word in base.split()),
            base[::-1],
            " ".join(reversed(base.split())),
        ]
    )
    if re.search(r"[a-z]", base):
        candidates.append(codecs.decode(base, "rot_13"))
    unique = tuple(dict.fromkeys(value for value in candidates if value))[:max_candidates]
    return NormalizedText(text, base, unique, frozenset(flags))
