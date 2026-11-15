"""
Tests for Amazon link parsing and short-link resolution (HTTP layer mocked: no network).
"""

import pytest

import amazon
from amazon import asin_from_url, slug_keywords

SLUG_URL = "https://www.amazon.it/Oral-B-Ultimate-Attorcigliate-Profondamente/dp/B0CXYZ1234/ref=sr_1_3?tag=aff-21&psc=1"


@pytest.mark.parametrize(
    "url, expected",
    [
        (SLUG_URL, "B0CXYZ1234"),
        ("https://amazon.it/dp/B0CXYZ1234", "B0CXYZ1234"),
        ("https://www.amazon.com/gp/product/B0CXYZ1234?th=1", "B0CXYZ1234"),
        ("https://www.amazon.co.uk/dp/b0cxyz1234/", "B0CXYZ1234"),
        ("http://www.amazon.de/-/en/dp/B0CXYZ1234", "B0CXYZ1234"),
        ("https://www.amazon.it/s?k=oral-b", None),
        ("https://www.amazon.it/dp/B0CXYZ12", None),
        ("https://amazon.evil.com/dp/B0CXYZ1234", None),
        ("https://evil.com/amazon.it/dp/B0CXYZ1234", None),
        ("https://amzn.to/3abcdef", None),
        ("not a url", None),
    ],
)
def test_asin_from_url(url, expected):
    assert asin_from_url(url) == expected


@pytest.mark.parametrize(
    "url, expected",
    [
        (SLUG_URL, "oral-b ultimate attorcigliate profondamente"),
        ("https://www.amazon.it/dp/B0CXYZ1234", None),
        ("https://www.amazon.it/gp/product/B0CXYZ1234", None),
    ],
)
def test_slug_keywords(url, expected):
    assert slug_keywords(url) == expected


async def test_short_link_resolves_to_amazon_url(http):
    redirects, requested = http
    redirects["https://amzn.to/3abc"] = "https://amzn.eu/d/xyz"
    redirects["https://amzn.eu/d/xyz"] = SLUG_URL

    assert await amazon.resolve_amazon_url("https://amzn.to/3abc") == SLUG_URL
    assert requested == ["https://amzn.to/3abc", "https://amzn.eu/d/xyz"]


async def test_direct_amazon_url_is_not_requested(http):
    _, requested = http
    assert await amazon.resolve_amazon_url(SLUG_URL) == SLUG_URL
    assert requested == []


async def test_redirect_to_non_amazon_host_is_not_followed(http):
    redirects, requested = http
    redirects["https://link.amazon/abc"] = "https://evil.example/dp/B0CXYZ1234"

    assert await amazon.resolve_amazon_url("https://link.amazon/abc") is None
    assert requested == ["https://link.amazon/abc"]


async def test_non_allowlisted_short_link_is_not_requested(http):
    _, requested = http
    assert await amazon.resolve_amazon_url("https://bit.ly/abc") is None
    assert await amazon.resolve_amazon_url("https://tidd.ly/abc") is None
    assert requested == []


async def test_relative_redirect_and_cache(http):
    redirects, requested = http
    redirects["https://amzn.eu/d/xyz"] = "/d/final"
    redirects["https://amzn.eu/d/final"] = "https://www.amazon.it/dp/B0CXYZ1234"

    for _ in range(2):
        assert await amazon.resolve_amazon_url("https://amzn.eu/d/xyz") == "https://www.amazon.it/dp/B0CXYZ1234"
    assert requested == ["https://amzn.eu/d/xyz", "https://amzn.eu/d/final"]


async def test_redirect_loop_gives_up(http):
    redirects, requested = http
    redirects["https://amzn.to/a"] = "https://amzn.to/b"
    redirects["https://amzn.to/b"] = "https://amzn.to/a"

    assert await amazon.resolve_amazon_url("https://amzn.to/a") is None
    assert len(requested) == amazon.MAX_HOPS


async def test_message_asin_by_url_reads_every_url(http):
    redirects, _ = http
    redirects["https://amzn.to/3abc"] = "https://www.amazon.it/dp/B0SHORT001"
    text = f"Offerta! {SLUG_URL}\nhttps://amzn.to/3abc). https://bit.ly/x"

    assert await amazon.message_asin_by_url(text) == {SLUG_URL: "B0CXYZ1234", "https://amzn.to/3abc": "B0SHORT001"}


@pytest.mark.parametrize(
    "answer, expected",
    [
        (SLUG_URL, ("B0CXYZ1234", SLUG_URL)),
        (f"Guarda questo prodotto: {SLUG_URL}", ("B0CXYZ1234", SLUG_URL)),
        ("https://amzn.eu/d/app", ("B0SHARE001", "https://www.amazon.it/Foo-Bar/dp/B0SHARE001")),
        ("oral-b ultimate", None),
        ("https://www.amazon.it/s?k=oral-b", None),
    ],
)
async def test_first_product_link_in_watch_answer(http, answer, expected):
    redirects, _ = http
    redirects["https://amzn.eu/d/app"] = "https://www.amazon.it/Foo-Bar/dp/B0SHARE001"
    assert await amazon.first_product_link(answer) == expected


async def test_intermediate_host_followed_only_after_a_short_link(http):
    redirects, requested = http
    redirects["https://link.amazon/B01abc"] = "https://amzlinks.in/B01abc"
    redirects["https://amzlinks.in/B01abc"] = "https://www.amazon.it/dp/B0GL22B4VQ?tag=aff-21"

    assert await amazon.resolve_amazon_url("https://link.amazon/B01abc") == "https://www.amazon.it/dp/B0GL22B4VQ?tag=aff-21"
    assert await amazon.resolve_amazon_url("https://amzlinks.in/other") is None
    assert requested == ["https://link.amazon/B01abc", "https://amzlinks.in/B01abc"]


async def test_transient_failure_is_not_cached(http, monkeypatch):
    calls = []

    def flaky(url):
        calls.append(url)
        if len(calls) == 1:
            raise TimeoutError("timed out")
        return "https://www.amazon.it/dp/B0CXYZ1234"

    monkeypatch.setattr(amazon, "_location", flaky)

    assert await amazon.resolve_amazon_url("https://amzn.to/flaky") is None
    assert await amazon.resolve_amazon_url("https://amzn.to/flaky") == "https://www.amazon.it/dp/B0CXYZ1234"


async def test_intermediate_host_cannot_chain_to_itself(http):
    redirects, requested = http
    redirects["https://link.amazon/x"] = "https://amzlinks.in/a"
    redirects["https://amzlinks.in/a"] = "https://amzlinks.in/b"

    assert await amazon.resolve_amazon_url("https://link.amazon/x") is None
    assert requested == ["https://link.amazon/x", "https://amzlinks.in/a"]


async def test_explicit_port_is_not_requested(http):
    _, requested = http
    assert await amazon.resolve_amazon_url("https://amzn.to:8443/abc") is None
    assert requested == []
