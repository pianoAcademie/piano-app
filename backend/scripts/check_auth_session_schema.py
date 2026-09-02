from __future__ import annotations

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from sqlalchemy import inspect

from app.db.session import engine


EXPECTED_COLUMNS = {
    "id",
    "user_id",
    "token_hash",
    "expires_at",
    "last_used_at",
    "revoked_at",
    "created_at",
}


def main() -> int:
    inspector = inspect(engine)
    if "auth_refresh_sessions" not in inspector.get_table_names():
        print("[ERROR] Missing table: auth_refresh_sessions")
        return 1

    actual_columns = {column["name"] for column in inspector.get_columns("auth_refresh_sessions")}
    missing_columns = sorted(EXPECTED_COLUMNS - actual_columns)
    if missing_columns:
        print(f"[ERROR] auth_refresh_sessions missing columns: {', '.join(missing_columns)}")
        return 1

    print("[OK] Authentication refresh-session schema is ready")
    return 0


if __name__ == "__main__":
    sys.exit(main())
