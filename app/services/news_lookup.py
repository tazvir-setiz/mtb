from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus, urlparse
from xml.etree import ElementTree

import httpx

logger = logging.getLogger(__name__)

ALLOWED_NEWS_DOMAINS = (
    "tasnimnews.com",
    "tasnimnews.ir",
    "farsnews.ir",
    "iribnews.ir",
)

_GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"
_MAX_RESULTS = 5


@dataclass(frozen=True)
class NewsEvidence:
    title: str
    source: str
    source_url: str
    published_at: datetime | None

    def as_context(self) -> dict:
        return {
            "title": self.title,
            "source": self.source,
            "source_url": self.source_url,
            "published_at": self.published_at.isoformat() if self.published_at else None,
        }


def _safe_domain(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == domain or host.endswith("." + domain) for domain in ALLOWED_NEWS_DOMAINS)


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        result = parsedate_to_datetime(value)
        if result.tzinfo is None:
            result = result.replace(tzinfo=timezone.utc)
        return result.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def _query_url(query: str) -> str:
    domain_query = " OR ".join(f"site:{domain}" for domain in ALLOWED_NEWS_DOMAINS)
    q = quote_plus(f"({domain_query}) {query}")
    return f"{_GOOGLE_NEWS_RSS}?q={q}&hl=fa&gl=IR&ceid=IR:fa"


async def search_latest_news(query: str, *, timeout_seconds: float = 8.0) -> tuple[NewsEvidence, ...]:
    query = (query or "").strip()
    if not query:
        return ()

    try:
        async with asyncio.timeout(timeout_seconds):
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(timeout_seconds, connect=min(4.0, timeout_seconds)),
                follow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0"},
            ) as client:
                response = await client.get(_query_url(query))
                response.raise_for_status()
    except Exception as exc:
        logger.info("News lookup failed type=%s", type(exc).__name__)
        return ()

    try:
        root = ElementTree.fromstring(response.text)
    except ElementTree.ParseError:
        return ()

    results: list[NewsEvidence] = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        published_at = _parse_date(item.findtext("pubDate"))
        source_node = item.find("source")
        source_name = ((source_node.text if source_node is not None else "") or "").strip()
        source_url = ((source_node.attrib.get("url") if source_node is not None else "") or "").strip()

        if not title or not source_url or not _safe_domain(source_url):
            continue

        results.append(
            NewsEvidence(
                title=title,
                source=source_name or urlparse(source_url).hostname or "news",
                source_url=source_url,
                published_at=published_at,
            )
        )

    results.sort(
        key=lambda x: x.published_at or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    return tuple(results[:_MAX_RESULTS])
