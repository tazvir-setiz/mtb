"""Bounded discovery; evidence is extracted only from verified publisher pages."""
from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from typing import Protocol
from urllib.parse import urljoin, urlsplit
from xml.etree import ElementTree

import httpx

MAX_BYTES = 256_000
MAX_CANDIDATES = 5
DISCOVERY_HOST = "news.google.com"


@dataclass(frozen=True)
class NewsCandidate:
    url: str


@dataclass(frozen=True)
class NewsEvidence:
    title: str
    source: str
    canonical_url: str
    published_at: datetime
    retrieved_at: datetime
    summary: str = ""
    relevance: float = 0.0

    def as_context(self):
        return {"title": self.title, "source": self.source,
                "canonical_url": self.canonical_url,
                "published_at": self.published_at.isoformat(),
                "retrieved_at": self.retrieved_at.isoformat(),
                "summary": self.summary, "relevance": self.relevance}


class NewsSearchProvider(Protocol):
    async def search(self, query: str, domains: tuple[str, ...]) -> tuple[NewsCandidate, ...]: ...
    async def extract(self, candidate: NewsCandidate, domains: tuple[str, ...]) -> NewsEvidence | None: ...


def allowed_url(url: str, domains: tuple[str, ...]) -> bool:
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower().rstrip(".")
        return bool(parsed.scheme == "https" and not parsed.username and not parsed.password
                    and parsed.port in (None, 443) and host in domains
                    and not parsed.fragment)
    except ValueError:
        return False


def parse_date(value: str) -> datetime | None:
    try:
        date = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            date = parsedate_to_datetime(value)
        except (ValueError, TypeError, OverflowError):
            return None
    if date.tzinfo is None:
        return None
    return date.astimezone(timezone.utc)


class ArticleMetadata(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.values = {}

    def handle_starttag(self, tag, attrs):
        if tag == "meta":
            attrs = dict(attrs)
            name = attrs.get("property", attrs.get("name", "")).lower()
            if name in {"og:title", "og:description", "description", "article:published_time", "datepublished"}:
                self.values.setdefault(name, attrs.get("content", "")[:1500])


async def public_host(host: str):
    addresses = await asyncio.get_running_loop().getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
        raise ValueError("non_public_address")


class GoogleNewsProvider:
    """RSS is discovery only. Opaque HTML/JS redirects are unsupported.

    Never decode undocumented Google tokens or trust RSS source labels.
    """
    def __init__(self, client: httpx.AsyncClient):
        self.client = client

    async def _get(self, url, domains, *, discovery=False):
        permitted = domains + ((DISCOVERY_HOST,) if discovery else ())
        for _ in range(4):
            if not allowed_url(url, permitted):
                raise ValueError("disallowed_url")
            await public_host(urlsplit(url).hostname)
            async with self.client.stream("GET", url, follow_redirects=False) as response:
                if response.is_redirect:
                    url = urljoin(url, response.headers.get("location", ""))
                    continue
                response.raise_for_status()
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > MAX_BYTES:
                        raise ValueError("response_too_large")
                return url, bytes(body).decode("utf-8", errors="replace")
        raise ValueError("too_many_redirects")

    async def search(self, query, domains):
        request = httpx.Request("GET", f"https://{DISCOVERY_HOST}/rss/search", params={
            "q": "(" + " OR ".join(f"site:{d}" for d in domains) + ") " + query,
            "hl": "fa", "gl": "IR", "ceid": "IR:fa",
        })
        _, xml = await self._get(str(request.url), (DISCOVERY_HOST,))
        if re.search(r"<!\s*(?:DOCTYPE|ENTITY)", xml, re.I):
            raise ValueError("unsafe_xml")
        root = ElementTree.fromstring(xml)
        links = dict.fromkeys((item.findtext("link") or "").strip() for item in root.findall(".//item"))
        return tuple(NewsCandidate(link) for link in links
                     if allowed_url(link, domains + (DISCOVERY_HOST,)))[:MAX_CANDIDATES]

    async def extract(self, candidate, domains):
        url, html = await self._get(candidate.url, domains, discovery=True)
        if not allowed_url(url, domains):
            return None
        parser = ArticleMetadata()
        parser.feed(html)
        values = parser.values
        title = values.get("og:title", "").strip()
        date = parse_date(values.get("article:published_time", values.get("datepublished", "")))
        if not title or not date:
            return None
        return NewsEvidence(title[:500], urlsplit(url).hostname, url, date,
                            datetime.now(timezone.utc),
                            values.get("og:description", values.get("description", ""))[:1000])
