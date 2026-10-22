"""Bluesky client boundary: the only module that talks to the network for the channel.

server.py never calls into this module for a dry run, so dry runs need no credentials and
make no network calls. Credentials come only from BLUESKY_HANDLE and BLUESKY_APP_PASSWORD.
Every atproto error is translated into one of the errors below, so callers can tell a bad
password (fix the config) from a rate limit (wait) without importing atproto themselves.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

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


def post(text: str) -> dict[str, str]:
    """Publish `text` and return {uri, cid}."""
    client = _login()
    try:
        created = client.send_post(text)
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
