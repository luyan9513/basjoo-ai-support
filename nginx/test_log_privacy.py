"""Nginx access-log privacy regression test."""

from pathlib import Path
import unittest


class NginxLogPrivacyTests(unittest.TestCase):
    def test_access_log_omits_query_string(self):
        nginx_config = Path(__file__).with_name("nginx.conf").read_text(
            encoding="utf-8"
        )

        self.assertNotIn('"$request"', nginx_config)
        self.assertIn('"$request_method $uri $server_protocol"', nginx_config)


if __name__ == "__main__":
    unittest.main()
