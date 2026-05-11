from __future__ import annotations

from pathlib import Path
import sys
import unittest
from types import SimpleNamespace

from fastapi import HTTPException

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.api.routes.quotes import _ensure_quote_editable


class QuoteEditabilityTests(unittest.TestCase):
    def test_created_quote_is_editable(self) -> None:
        _ensure_quote_editable(SimpleNamespace(status="created"))

    def test_change_requested_quote_is_editable(self) -> None:
        _ensure_quote_editable(SimpleNamespace(status="change_requested"))

    def test_sent_quote_is_not_editable(self) -> None:
        with self.assertRaises(HTTPException):
            _ensure_quote_editable(SimpleNamespace(status="sent"))


if __name__ == "__main__":
    unittest.main()
