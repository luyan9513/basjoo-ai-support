"""Regression tests for URL ingestion SSRF boundaries."""

import socket

from services import url_safety


def address_info(address: str):
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    sockaddr = (address, 0, 0, 0) if family == socket.AF_INET6 else (address, 0)
    return (family, socket.SOCK_STREAM, 6, "", sockaddr)


def test_benchmark_network_is_blocked():
    assert url_safety._is_unsafe_ip("198.18.0.1") is True
    assert url_safety._is_unsafe_ip("198.19.255.254") is True


def test_mixed_dns_answer_is_blocked(monkeypatch):
    monkeypatch.setattr(
        url_safety.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            address_info("93.184.216.34"),
            address_info("127.0.0.1"),
        ],
    )

    allowed, reason = url_safety.validate_url_safe("https://mixed.example/path")

    assert allowed is False
    assert "blocked IP" in reason


def test_mixed_ipv4_ipv6_answer_is_blocked(monkeypatch):
    monkeypatch.setattr(
        url_safety.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            address_info("93.184.216.34"),
            address_info("::1"),
        ],
    )

    allowed, reason = url_safety.validate_url_safe("https://dual-stack.example/path")

    assert allowed is False
    assert "blocked IP" in reason


def test_public_dns_answer_is_allowed_without_caching(monkeypatch):
    answers = [
        [address_info("93.184.216.34")],
        [address_info("127.0.0.1")],
    ]
    monkeypatch.setattr(
        url_safety.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: answers.pop(0),
    )

    assert url_safety.validate_url_safe("https://rebind.example/path")[0] is True
    assert url_safety.validate_url_safe("https://rebind.example/path")[0] is False


def test_url_log_reference_does_not_expose_path_or_query():
    raw_url = "https://example.com/private/order?token=top-secret"

    log_reference = url_safety.url_log_reference(raw_url)

    assert "top-secret" not in log_reference
    assert "/private/order" not in log_reference
    assert "example.com" in log_reference
    assert "url_hash=" in log_reference
