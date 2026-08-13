from __future__ import annotations

import unittest
from pathlib import Path
import runpy

redact_line = runpy.run_path(str(Path(__file__).with_name("redact-existing-access-logs.py")))["redact_line"]


class RedactExistingAccessLogsTests(unittest.TestCase):
    def test_removes_request_query_and_referrer(self) -> None:
        line = (
            '127.0.0.1 - - [13/Aug/2026:12:00:00 +0000] '
            '"GET /reset?token=secret&email=a%40b.fr HTTP/1.1" 200 42 '
            '"https://app.example/path?payment_token=secret" "Browser"\n'
        )
        redacted, changed = redact_line(line)
        self.assertTrue(changed)
        self.assertIn('"GET /reset HTTP/1.1"', redacted)
        self.assertIn('"-" "Browser"', redacted)
        self.assertNotIn("secret", redacted)
        self.assertNotIn("email=", redacted)


if __name__ == "__main__":
    unittest.main()
