from __future__ import annotations

from types import SimpleNamespace
import unittest

from app.main import _safe_request_query


class RequestLoggingSecurityTests(unittest.TestCase):
    def test_query_values_are_redacted(self) -> None:
        request = SimpleNamespace(query_params={"token": "secret-value", "return_to": "/client", "page": "2"})
        value = _safe_request_query(request)
        self.assertEqual(value, "page=[REDACTED]&return_to=[REDACTED]&token=[REDACTED]")
        self.assertNotIn("secret-value", value)
        self.assertNotIn("/client", value)


if __name__ == "__main__":
    unittest.main()
