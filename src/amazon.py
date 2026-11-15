"""
Amazon product links: ASIN parsing and short-link resolution.

Channel URLs are untrusted: only Amazon short-link hosts (and the redirectors they
hop through) are ever requested, the
host allowlist is checked on every redirect hop, and Amazon pages themselves are
never fetched (the ASIN is parsed from the URL).
"""

import asyncio
import logging
import re
import urllib.request
from urllib.error import HTTPError
from urllib.parse import urljoin, urlsplit

log = logging.getLogger(__name__)

SHORT_LINK_HOSTS = {"link.amazon", "amzn.to", "amzn.eu"}
# Followed only as a redirect straight from a short link, never requested when a post links to them directly.
# amzlinks.in (Button, Inc.) sits between link.amazon and amazon.it.
REDIRECT_HOSTS = {"amzlinks.in"}
MAX_HOPS = 3
_TIMEOUT = 5  # seconds per request
_CACHE_MAX = 2000
_URL_RE = re.compile(r"https?://[^\s<>\"']+")

_AMAZON_HOST_RE = re.compile(r"(?:www\.|m\.|smile\.)?amazon\.(?:[a-z]{2,3}|co\.[a-z]{2}|com\.[a-z]{2})")
_ASIN_PATH_RE = re.compile(r"/(?:dp|gp/product)/([a-z0-9]{10})(?:[/?]|$)", re.IGNORECASE)
_SLUG_PATH_RE = re.compile(r"^/([^/]+)/dp/", re.IGNORECASE)


def _amazon_parts(url: str):
    parts = urlsplit(url)
    if parts.scheme in ("http", "https") and _AMAZON_HOST_RE.fullmatch((parts.hostname or "").lower()):
        return parts
    return None


def asin_from_url(url: str) -> str | None:
    """ASIN of a direct Amazon product URL (/dp/<ASIN>, /gp/product/<ASIN>), else None. No request."""
    parts = _amazon_parts(url)
    match = parts and _ASIN_PATH_RE.search(parts.path)
    return match.group(1).upper() if match else None


def slug_keywords(url: str) -> str | None:
    """Keywords from the product slug of an Amazon URL ('/Oral-B-Ultimate/dp/…' -> 'oral-b ultimate')."""
    parts = _amazon_parts(url)
    match = parts and _SLUG_PATH_RE.match(parts.path)
    if not match or match.group(1) == "-":
        return None
    words: list[str] = []
    for token in match.group(1).lower().split("-"):
        # shortcut: a 1-char token is glued to the previous word ('oral-b'); slugs lose real hyphens otherwise
        if len(token) == 1 and words:
            words[-1] += "-" + token
        elif token:
            words.append(token)
    return " ".join(words) or None


def urls_in_text(text: str) -> list[str]:
    return [url.rstrip(".,;:!?)]") for url in _URL_RE.findall(text)]


def _loggable(url: str) -> str:
    """Host and path only: affiliate query strings never reach the logs."""
    parts = urlsplit(url)
    return f"{parts.hostname}{parts.path}"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None  # 3xx surfaces as HTTPError: each hop is checked against the allowlist first


_opener = urllib.request.build_opener(_NoRedirect)


def _location(url: str) -> str | None:
    """Location header of one request to url, or None for a final answer (blocking: run it in a thread).

    Raises OSError on transient failures (network, timeout, 5xx), so they are not cached.
    """
    # GET, not HEAD: link.amazon answers HEAD with 404. The body is never read.
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with _opener.open(request, timeout=_TIMEOUT):
            return None
    except HTTPError as e:
        if 300 <= e.code < 400:
            return e.headers.get("Location")
        if e.code >= 500:
            raise
        return None


_cache: dict[str, str | None] = {}


async def resolve_amazon_url(url: str) -> str | None:
    """Final Amazon URL of a direct or short Amazon link, else None. Results cached per URL."""
    if url in _cache:
        return _cache[url]
    current, resolved, previous_host = url, None, None
    for hop in range(MAX_HOPS + 1):
        if _amazon_parts(current):
            resolved = current
            break
        parts = urlsplit(current)
        host = (parts.hostname or "").lower()
        if parts.scheme not in ("http", "https") or parts.port is not None:
            break
        if host not in SHORT_LINK_HOSTS and not (host in REDIRECT_HOSTS and previous_host in SHORT_LINK_HOSTS):
            break
        if hop == MAX_HOPS:
            log.warning("Short link %s: too many redirects", _loggable(url))
            break
        try:
            location = await asyncio.to_thread(_location, current)
        except (OSError, ValueError) as e:
            log.warning("Short link %s not resolved: %s", _loggable(current), e)
            return None
        if not location:
            break
        current, previous_host = urljoin(current, location), host
    if len(_cache) >= _CACHE_MAX:
        _cache.clear()  # shortcut: drop-all eviction, fine for a few thousand links a day; LRU if it grows
    _cache[url] = resolved
    return resolved


async def _linked_products(text: str):
    """(url, asin, amazon_url) for each product URL in text: direct ones parsed, short links resolved."""
    for url in dict.fromkeys(urls_in_text(text)):
        resolved = await resolve_amazon_url(url)
        if resolved and (asin := asin_from_url(resolved)):
            yield url, asin, resolved


async def message_asins(text: str) -> dict[str, str]:
    """ASIN of each URL in a channel message that links to an Amazon product, keyed by the URL as written."""
    return {url: asin async for url, asin, _ in _linked_products(text)}


async def first_product_link(text: str) -> tuple[str, str] | None:
    """(asin, amazon_url) of the first Amazon product linked in a user's /watch answer."""
    async for _, asin, resolved in _linked_products(text):
        return asin, resolved
    return None
