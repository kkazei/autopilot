"""Bluesky client tests (D1-C): credentials from env only, one login per process, clear error types.

A fake atproto client stands in for the network; nothing here posts.
"""

from __future__ import annotations

from types import SimpleNamespace

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
        self.deleted: list[str] = []

    def login(self, handle, password):
        self.logins.append((handle, password))
        if self.fail_with:
            raise self.fail_with

    def send_post(self, text):
        self.sent.append(text)
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
