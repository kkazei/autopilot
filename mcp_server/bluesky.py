"""Bluesky client boundary. P1 ships the interface only; the live atproto client is deferred.

server.py never calls into this module for a dry run, so dry runs need no credentials and
make no network calls. A live call raises instead of pretending to post, so a missing client
can never look like a successful publish.
"""

from __future__ import annotations


class BlueskyError(RuntimeError):
    """Base class, so callers can mark a post failed without catching unrelated errors."""


class BlueskyAuthError(BlueskyError):
    pass


class BlueskyRateLimitError(BlueskyError):
    pass


class BlueskyNotAvailable(BlueskyError):
    pass


_DEFERRED = "the live Bluesky client is not implemented yet; use DRY_RUN=1"


def post(text: str) -> dict[str, str]:
    """Will return {uri, cid} once the atproto client lands."""
    raise BlueskyNotAvailable(_DEFERRED)


def get_post_metrics(uri: str) -> dict[str, int]:
    """Will return {likes, reposts, replies} once the atproto client lands."""
    raise BlueskyNotAvailable(_DEFERRED)


def delete_post(uri: str) -> None:
    """For cleaning up test posts once the atproto client lands."""
    raise BlueskyNotAvailable(_DEFERRED)
