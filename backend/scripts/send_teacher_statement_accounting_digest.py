from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.db.session import SessionLocal
from app.services.teacher_statement_notifications import run_teacher_statement_accounting_digest_job


def main() -> int:
    parser = argparse.ArgumentParser(description="Send the approved monthly teacher statement digest to accounting.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Send immediately, bypassing the normal cutoff and duplicate guard.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Compute the digest without sending an email.")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        sent = run_teacher_statement_accounting_digest_job(
            db,
            now=datetime.now(timezone.utc),
            dry_run=args.dry_run,
            force=args.force,
        )
        if args.dry_run:
            db.rollback()
        else:
            db.commit()
        print(f"teacher_statement_accounting_digest_sent={sent}")
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
