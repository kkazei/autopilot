"""Offline guard for every test: no external network, so tests can never spend quota or post.

Loopback stays allowed because the MCP stdio tests (and later the mock LLM) run locally.
Tests marked `live` opt out; they run only in phase P5, with explicit authorization.
This guards the test process only; subprocesses are covered by their own egress checks.
"""

from __future__ import annotations

import ipaddress
import socket

import pytest

_real_connect = socket.socket.connect
_real_connect_ex = socket.socket.connect_ex


def _is_loopback(address: object) -> bool:
    host = address[0] if isinstance(address, tuple) else address
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(str(host)).is_loopback
    except ValueError:
        return False


def _check(sock: socket.socket, address: object) -> None:
    if sock.family in (socket.AF_INET, socket.AF_INET6) and not _is_loopback(address):
        raise ConnectionRefusedError(f"external network blocked in tests: {address!r}")


@pytest.fixture(autouse=True)
def _block_external_network(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    if request.node.get_closest_marker("live"):
        return

    def connect(self: socket.socket, address: object) -> None:
        _check(self, address)
        return _real_connect(self, address)

    def connect_ex(self: socket.socket, address: object) -> int:
        _check(self, address)
        return _real_connect_ex(self, address)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", connect_ex)
