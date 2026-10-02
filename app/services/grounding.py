"""On-demand resolution with injectable transport and conservative event matching."""
import asyncio
import logging
import re
import time
from dataclasses import dataclass, replace
from datetime import datetime, timezone

import httpx

from app.services.news_lookup import GoogleNewsProvider, NewsEvidence, allowed_url

logger = logging.getLogger(__name__)
STOP_WORDS = frozenset("از به در با و که را یک این آن است شد شده برای می the a in at on of and".split())


def words(text):
    text = text.lower().replace("ي", "ی").replace("ك", "ک")
    return [word for word in re.findall(r"[^\W\d_]+", text, re.UNICODE)
            if len(word) > 1 and word not in STOP_WORDS]


def minimal_query(query, original):
    """Only short, original keywords; never URLs, handles or contact details."""
    redacted = re.sub(r"https?://\S+|\S+@\S+|@\S+|\+?[\d۰-۹][\d۰-۹\s()-]{5,}", " ", original)
    allowed = set(words(redacted))
    tokens = list(dict.fromkeys(words(query)))
    if not 3 <= len(tokens) <= 10 or any(word not in allowed for word in tokens):
        return ""
    return " ".join(tokens)[:120]


@dataclass(frozen=True)
class GroundingResult:
    status: str
    evidence: tuple[NewsEvidence, ...] = ()
    reason: str = ""
    # Retrieval match is not a truth or semantic-resolution guarantee.
    ambiguity_resolved: bool = False


class GroundingService:
    def __init__(self, provider=None, *, max_age_hours=72):
        self.provider = provider
        self.max_age_hours = max_age_hours

    async def resolve(self, query, original, domains, *, timeout_seconds=8):
        query = minimal_query(query, original)
        if not query or not domains:
            return GroundingResult("unavailable", reason="invalid_query_or_domains")
        started = time.monotonic()
        try:
            async with asyncio.timeout(timeout_seconds):
                if self.provider is not None:
                    result = await self._resolve(self.provider, query, domains)
                else:
                    async with httpx.AsyncClient(timeout=min(4, timeout_seconds),
                                                 follow_redirects=False, trust_env=False) as client:
                        result = await self._resolve(GoogleNewsProvider(client), query, domains)
        except Exception as exc:
            result = GroundingResult("unavailable", reason=type(exc).__name__)
        logger.info("Guard grounding status=%s hits=%d reason=%s latency=%.3f age_hours=%s",
                    result.status, len(result.evidence), result.reason, time.monotonic() - started,
                    (datetime.now(timezone.utc) - result.evidence[0].published_at).total_seconds() / 3600
                    if result.evidence else None)
        return result

    async def _resolve(self, provider, query, domains):
        from xml.etree.ElementTree import ParseError

        try:
            candidates = await provider.search(query, domains)
        except ParseError:
            return GroundingResult("unavailable", reason="malformed_search")
        relevant = []
        seen = set()
        anchors = set(words(query))
        now = datetime.now(timezone.utc)
        for candidate in candidates[:5]:
            try:
                item = await provider.extract(candidate, domains)
            except (httpx.HTTPError, OSError, ValueError):
                continue
            if item is None or not allowed_url(item.canonical_url, domains):
                continue
            if item.canonical_url in seen or not item.published_at or item.published_at.tzinfo is None:
                continue
            seen.add(item.canonical_url)
            age = (now - item.published_at).total_seconds() / 3600
            if age < -0.1 or age > self.max_age_hours:
                continue
            # All event anchors must match. Semantic identity still needs judging.
            overlap = anchors & set(words(item.title))
            if overlap != anchors:
                continue
            relevant.append(replace(item, relevance=len(overlap) / len(anchors)))
        relevant.sort(key=lambda item: (item.relevance, item.published_at), reverse=True)
        if not relevant:
            return GroundingResult("no_match", reason="no_fresh_matching_article")
        if len({tuple(words(item.title)) for item in relevant}) > 1:
            return GroundingResult("ambiguous", reason="different_matching_reports")
        # One article per resolution prevents cross-article fact merging.
        return GroundingResult("candidate", (relevant[0],), "requires_semantic_verification")
