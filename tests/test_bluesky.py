"""Bluesky client tests (D1-C): credentials from env only, one login per process, clear error types.

A fake atproto client stands in for the network; nothing here posts.
"""

from __future__ import annotations

import random
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest
from atproto_client import exceptions as ex

from mcp_server import bluesky

HANDLE = "bakery.test"
PASSWORD = "abcd-efgh-ijkl-mnop"
URI = "at://did:plc:abc/app.bsky.feed.post/3k"


class FakeClient:
    def __init__(self, fail_with: Exception | None = None, posts: list | None = None) -> None:
        self.fail_with = fail_with
        self.posts = posts if posts is not None else [
            SimpleNamespace(like_count=4, repost_count=1, reply_count=None)]
        self.logins: list[tuple[str, str]] = []
        self.sent: list[str] = []
        self.send_calls: list[tuple[tuple, dict]] = []
        self.deleted: list[str] = []

    def login(self, handle, password):
        self.logins.append((handle, password))
        if self.fail_with:
            raise self.fail_with

    def send_post(self, *args, **kwargs):
        self.sent.append(args[0])
        self.send_calls.append((args, kwargs))
        self.facets = kwargs.get("facets")
        return SimpleNamespace(uri=URI, cid="bafy1")

    def get_posts(self, uris):
        return SimpleNamespace(posts=self.posts)

    def delete_post(self, uri):
        self.deleted.append(uri)
        return True


@pytest.fixture
def fake(monkeypatch) -> FakeClient:
    client = FakeClient()
    monkeypatch.setenv(bluesky.HANDLE_ENV, HANDLE)
    monkeypatch.setenv(bluesky.PASSWORD_ENV, PASSWORD)
    monkeypatch.setattr(bluesky, "_make_client", lambda: client)
    bluesky.reset()
    yield client
    bluesky.reset()


def test_post_returns_uri_and_cid_using_env_credentials(fake):
    assert bluesky.post("Fresh rye at 7.") == {"uri": URI, "cid": "bafy1"}
    assert fake.logins == [(HANDLE, PASSWORD)] and fake.sent == ["Fresh rye at 7."]


def test_url_gets_a_link_facet_with_utf8_byte_offsets(fake):
    text = "It’s Saturday — join us: https://example.com/class."
    bluesky.post(text)
    (facet,) = fake.facets
    raw = text.encode("utf-8")
    start, end = facet.index.byte_start, facet.index.byte_end
    assert raw[start:end] == b"https://example.com/class"
    assert start != text.index("https")  # character offset would be wrong: multi-byte chars precede it
    assert facet.features[0].uri == "https://example.com/class"


def test_post_without_url_sends_no_facets(fake):
    bluesky.post("Fresh rye at 7.")
    assert fake.send_calls == [(("Fresh rye at 7.",), {})]  # exactly the pre-facet call


@pytest.mark.parametrize("text, urls", [
    # offsets: multi-byte text before, between, and around URLs
    ("🍞 パン été — https://example.com/a", ["https://example.com/a"]),
    ("https://a.com/x ’ café 🍞 https://b.com/y", ["https://a.com/x", "https://b.com/y"]),
    ("https://a.com start end https://b.com", ["https://a.com", "https://b.com"]),
    ("https://x.com/a and again https://x.com/a", ["https://x.com/a", "https://x.com/a"]),
    # boundaries: sentence punctuation, quotes and brackets around the URL are not part of it
    ("go https://x.com/a. https://x.com/b, (https://x.com/c) [https://x.com/d] \"https://x.com/e\" 'https://x.com/f'!",
     [f"https://x.com/{c}" for c in "abcdef"]),
    ("Book “https://example.com/class” now ‘https://example.com/b’", ["https://example.com/class", "https://example.com/b"]),
    ("Link: https://example.com/class… and https://example.com/a—next https://example.com/b。",
     ["https://example.com/class", "https://example.com/a", "https://example.com/b"]),
    ("<https://x.com/a>", ["https://x.com/a"]),
    ("https://x.com/a?b=1&c=2#frag.", ["https://x.com/a?b=1&c=2#frag"]),
    ("See https://en.wikipedia.org/wiki/Bread_(food) and (https://en.wikipedia.org/wiki/Rye_(grain)).",
     ["https://en.wikipedia.org/wiki/Bread_(food)", "https://en.wikipedia.org/wiki/Rye_(grain)"]),
    ("HTTPS://EXAMPLE.COM/A", ["HTTPS://EXAMPLE.COM/A"]),
    # no host, or a URL we cannot represent: no link rather than a broken one, and never an exception
    ("try https://... or https://) or https://[x.com", []),
    ("https://example.com/café", []),
    ("https://example.com/café and https://x.com/a🍞", ["https://x.com/a"]),  # combining accent; emoji ends it
    ("visit example.com/class", []),  # bare domains are not linked (accepted gap)
])
def test_link_spans_cover_exactly_the_url(text, urls):
    raw = text.encode("utf-8")
    spans = bluesky.link_spans(text)
    assert [u for _, _, u in spans] == urls
    assert all(raw[s:e].decode("utf-8") == u for s, e, u in spans)


def _random_post(rng: random.Random) -> str:
    pieces = ["rye", "Saturday", "7am", "’", "—", "🍞", "パン", "é", "…", "(", ")", ".", ",", "“", "”",
              "https://bakery.example/class", "https://x.com/a?b=1#c", "https://en.wikipedia.org/wiki/Rye_(grain)",
              "http://a.co", "https://"]
    return "".join(rng.choice(pieces) + rng.choice(["", " ", " ", "\n"]) for _ in range(rng.randint(0, 25)))


def test_link_spans_invariants_on_random_text():
    rng = random.Random(4242)
    for _ in range(300):
        text = _random_post(rng)
        raw = text.encode("utf-8")
        prev_end = 0
        for start, end, url in bluesky.link_spans(text):
            assert prev_end <= start < end <= len(raw), ascii(text)
            assert raw[start:end].decode("utf-8") == url, ascii(text)
            parts = urlsplit(url)
            assert parts.scheme.lower() in ("http", "https") and parts.hostname, ascii(text)
            assert url.isascii() and not any(c.isspace() for c in url), ascii(text)
            prev_end = end


def test_facet_build_failure_is_a_bluesky_error_and_nothing_is_sent(fake, monkeypatch):
    def broken(text):
        raise ValueError(f"bad facet near {PASSWORD}")
    monkeypatch.setattr(bluesky, "_facets", broken)
    with pytest.raises(bluesky.BlueskyError) as info:
        bluesky.post("Class: https://example.com/class")
    assert fake.sent == [] and PASSWORD not in str(info.value)


def test_session_is_reused_across_calls(fake):
    bluesky.post("one")
    bluesky.get_post_metrics(URI)
    bluesky.delete_post(URI)
    assert len(fake.logins) == 1 and fake.deleted == [URI]


def test_metrics_map_counts_and_treat_missing_as_zero(fake):
    assert bluesky.get_post_metrics(URI) == {"likes": 4, "reposts": 1, "replies": 0}


def test_metrics_for_unknown_post_raise_not_found(fake):
    fake.posts = []
    with pytest.raises(bluesky.BlueskyNotFound):
        bluesky.get_post_metrics(URI)


@pytest.mark.parametrize("missing", [bluesky.HANDLE_ENV, bluesky.PASSWORD_ENV])
def test_missing_credentials_raise_auth_error_before_any_network(fake, monkeypatch, missing):
    monkeypatch.delenv(missing)
    with pytest.raises(bluesky.BlueskyAuthError, match="must both be set"):
        bluesky.post("hi")
    assert fake.logins == []


@pytest.mark.parametrize("error, expected", [
    (ex.UnauthorizedError(None), bluesky.BlueskyAuthError),
    (ex.RateLimitExceededError(None), bluesky.BlueskyRateLimitError),
    (ex.NetworkError(None), bluesky.BlueskyError),
    (ex.BadRequestError(None), bluesky.BlueskyError),
])
def test_atproto_errors_are_translated(fake, error, expected):
    fake.fail_with = error
    with pytest.raises(expected):
        bluesky.post("hi")


def test_failed_login_is_not_cached(fake):
    fake.fail_with = ex.UnauthorizedError(None)
    with pytest.raises(bluesky.BlueskyAuthError):
        bluesky.post("hi")
    fake.fail_with = None
    bluesky.post("hi")
    assert len(fake.logins) == 2


def test_error_messages_never_contain_the_app_password(fake, monkeypatch):
    fake.fail_with = RuntimeError(f"server echoed {PASSWORD}")
    with pytest.raises(bluesky.BlueskyError) as info:
        bluesky.post("hi")
    assert PASSWORD not in str(info.value)
