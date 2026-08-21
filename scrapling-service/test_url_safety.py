"""Service-local SSRF and DNS pinning regression tests."""

import socket
import unittest
from unittest.mock import MagicMock, patch

import main


def address_info(address: str):
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    sockaddr = (address, 0, 0, 0) if family == socket.AF_INET6 else (address, 0)
    return (family, socket.SOCK_STREAM, 6, "", sockaddr)


class UrlSafetyTests(unittest.TestCase):
    def test_benchmark_network_is_blocked(self):
        self.assertTrue(main._is_unsafe_ip("198.18.0.1"))
        self.assertTrue(main._is_unsafe_ip("198.19.255.254"))

    def test_mixed_ipv4_ipv6_answer_is_blocked(self):
        with patch.object(
            main.socket,
            "getaddrinfo",
            return_value=[address_info("93.184.216.34"), address_info("::1")],
        ):
            with self.assertRaises(ValueError):
                main._validate_fetch_url_safe("https://dual-stack.example/path")

    def test_safe_redirect_fetch_pins_the_validated_dns_answer(self):
        response = MagicMock(
            status_code=200,
            text="ok",
            url="https://example.com/path",
            headers={"content-type": "text/plain"},
        )
        getter = MagicMock(return_value=response)
        with patch.object(
            main.socket,
            "getaddrinfo",
            return_value=[address_info("93.184.216.34")],
        ) as resolver:
            result = main._fetch_following_safe_redirects(
                "https://example.com/path", 30, getter
            )

        self.assertEqual(result[0], "ok")
        getter.assert_called_once_with(
            "https://example.com/path", 30, ("93.184.216.34",)
        )
        resolver.assert_called_once()

    def test_curl_uses_validated_ip_without_re_resolving(self):
        response = MagicMock()
        with patch.object(main.curl_requests, "get", return_value=response) as request:
            result = main._curl_get(
                "https://example.com/path", 30, ("93.184.216.34",)
            )

        self.assertIs(result, response)
        curl_options = request.call_args.kwargs["curl_options"]
        resolve_rules = curl_options[main.CurlOpt.RESOLVE]
        self.assertEqual(resolve_rules, ["example.com:443:93.184.216.34"])

    def test_redirect_to_private_address_is_blocked(self):
        redirect = MagicMock(
            status_code=302,
            text="",
            url="https://example.com/start",
            headers={"location": "http://127.0.0.1/admin"},
        )
        getter = MagicMock(return_value=redirect)
        with patch.object(
            main.socket,
            "getaddrinfo",
            return_value=[address_info("93.184.216.34")],
        ):
            with self.assertRaises(ValueError):
                main._fetch_following_safe_redirects(
                    "https://example.com/start", 30, getter
                )

    def test_url_log_reference_omits_path_and_query(self):
        raw_url = "https://example.com/private/order?token=top-secret"

        log_reference = main._url_log_reference(raw_url)

        self.assertNotIn("top-secret", log_reference)
        self.assertNotIn("/private/order", log_reference)
        self.assertIn("example.com", log_reference)
        self.assertIn("url_hash=", log_reference)


if __name__ == "__main__":
    unittest.main()
