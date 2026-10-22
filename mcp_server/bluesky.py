"""Bluesky client boundary: the only module that talks to the network for the channel.

server.py never calls into this module for a dry run, so dry runs need no credentials and
make no network calls. Credentials come only from BLUESKY_HANDLE and BLUESKY_APP_PASSWORD.
Every atproto error is translated into one of the errors below, so callers can tell a bad
password (fix the config) from a rate limit (wait) without importing atproto themselves.
"""

from __future__ import annotations

import os
import re
import unicodedata
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from harness.trace import redact

if TYPE_CHECKING:
    from atproto import Client

HANDLE_ENV = "BLUESKY_HANDLE"
PASSWORD_ENV = "BLUESKY_APP_PASSWORD"

_client: Client | None = None


class BlueskyError(RuntimeError):
    """Base class, so callers can mark a post failed without catching unrelated errors."""


class BlueskyAuthError(BlueskyError):
    """Missing or rejected credentials. Retrying will not help; the config must change."""


class BlueskyRateLimitError(BlueskyError):
    def __init__(self, message: str, retry_after_s: float | None = None) -> None:
        super().__init__(message)
        self.retry_after_s = retry_after_s


class BlueskyNotFound(BlueskyError):
    pass


def _make_client() -> Client:
    """atproto is imported here, not at module load, so dry runs and agent-role servers never pay for it."""
    from atproto import Client

    return Client()


def _translate(e: Exception) -> BlueskyError:
    from atproto_client import exceptions as ex

    message = redact(f"{type(e).__name__}: {e}")
    if isinstance(e, ex.RateLimitExceededError):
        return BlueskyRateLimitError(f"Bluesky rate limit hit: {message}", e.retry_after)
    if isinstance(e, ex.UnauthorizedError) or (
        isinstance(e, ex.RequestErrorBase) and e.response is not None and e.response.status_code == 401
    ):
        return BlueskyAuthError(f"Bluesky rejected the credentials: {message}")
    if isinstance(e, ex.NetworkError):
        return BlueskyError(f"Bluesky network error: {message}")
    return BlueskyError(f"Bluesky error: {message}")


def _login() -> Client:
    """One session per process: createSession has its own tight rate limit, so logging in per call would hit it."""
    global _client
    if _client is not None:
        return _client
    handle = os.environ.get(HANDLE_ENV, "")
    password = os.environ.get(PASSWORD_ENV, "")
    if not handle or not password:
        raise BlueskyAuthError(f"{HANDLE_ENV} and {PASSWORD_ENV} must both be set")
    client = _make_client()
    try:
        client.login(handle, password)
    except Exception as e:
        raise _translate(e) from None
    _client = client
    return client


def reset() -> None:
    """Forget the session (tests, or after an auth error so the next call logs in again)."""
    global _client
    _client = None


# Only characters RFC 3986 allows, so curly quotes, em dashes, ellipses and "<>" glued to a URL end it.
_URL_RE = re.compile(r"https?://[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]+", re.IGNORECASE)
_TRAILING_PUNCT = ".,;:!?')]"
_OPENER = {")": "(", "]": "["}


def _trim(url: str) -> str:
    """Drop sentence punctuation after a URL, but keep a closing bracket the URL itself opened (Wikipedia style)."""
    while url and url[-1] in _TRAILING_PUNCT:
        opener = _OPENER.get(url[-1])
        if opener and url.count(opener) >= url.count(url[-1]):
            break
        url = url[:-1]
    return url


def _has_host(url: str) -> bool:
    try:
        return bool(urlsplit(url).hostname)
    except ValueError:  # e.g. an unclosed "[": no link is better than failing the whole post
        return False


def link_spans(text: str) -> list[tuple[int, int, str]]:
    """Find URLs as (byte_start, byte_end, url).

    Bluesky only renders a link when the post carries a facet, and facet offsets are UTF-8
    bytes, not characters, so a curly quote or emoji before the URL would shift a
    character-based offset. A URL that runs into a non-ASCII letter, digit or accent (an IRI
    such as /café) is skipped: linking the truncated ASCII part would send readers to the
    wrong page. Never raises for text a Draft can hold, because post() would turn that into
    a failed post.
    """
    spans = []
    for m in _URL_RE.finditer(text):
        after = text[m.end(): m.end() + 1]
        if after and unicodedata.category(after)[0] in "LMN":
            continue
        url = _trim(m.group())
        if not _has_host(url):
            continue
        start = len(text[: m.start()].encode("utf-8"))
        spans.append((start, start + len(url.encode("utf-8")), url))
    return spans


def _facets(text: str) -> list:
    from atproto import models

    return [
        models.AppBskyRichtextFacet.Main(
            index=models.AppBskyRichtextFacet.ByteSlice(byte_start=start, byte_end=end),
            features=[models.AppBskyRichtextFacet.Link(uri=url)],
        )
        for start, end, url in link_spans(text)
    ]


def post(text: str) -> dict[str, str]:
    """Publish `text` and return {uri, cid}."""
    client = _login()
    try:
        facets = _facets(text)
        created = client.send_post(text, facets=facets) if facets else client.send_post(text)
    except Exception as e:
        raise _translate(e) from None
    return {"uri": created.uri, "cid": created.cid}


def get_post_metrics(uri: str) -> dict[str, int]:
    """Return {likes, reposts, replies}; a deleted or unknown post raises BlueskyNotFound instead of reporting zeros."""
    client = _login()
    try:
        posts = client.get_posts([uri]).posts
    except Exception as e:
        raise _translate(e) from None
    if not posts:
        raise BlueskyNotFound(f"post not found: {uri}")
    view = posts[0]
    return {"likes": view.like_count or 0, "reposts": view.repost_count or 0, "replies": view.reply_count or 0}


def delete_post(uri: str) -> None:
    """For cleaning up test posts."""
    client = _login()
    try:
        client.delete_post(uri)
    except Exception as e:
        raise _translate(e) from None
