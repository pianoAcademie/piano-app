from __future__ import annotations

import argparse
import os
import sys
from uuid import UUID

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.user import User, UserRole
from app.services.client_portal_access import send_client_portal_access_email


SCRIPT_PREFIX = "PROD_CLIENT_PORTAL_ACCESS"


def _print(message: str) -> None:
    print(f"[{SCRIPT_PREFIX}] {message}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Send one secure client portal password-setup email in production.",
    )
    parser.add_argument("--client-id", type=UUID, required=True)
    parser.add_argument("--expected-email", required=True)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually create the single-use token and send the email.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    expected_email = args.expected_email.strip().lower()

    with SessionLocal() as db:
        client = db.scalar(
            select(User).where(
                User.id == args.client_id,
                User.role == UserRole.CLIENT,
            )
        )
        if client is None:
            raise SystemExit(f"[{SCRIPT_PREFIX}] client not found")
        if client.email.strip().lower() != expected_email:
            raise SystemExit(f"[{SCRIPT_PREFIX}] expected email does not match the client")

        _print(
            "validated "
            f"client_id={client.id} email={client.email} "
            f"language={client.preferred_language or 'fr'} apply={args.apply}"
        )
        if not args.apply:
            _print("dry-run complete; no token created and no email sent")
            return

        try:
            message_id = send_client_portal_access_email(
                db,
                user=client,
                password_setup_required=True,
                source="CLIENT_PORTAL_ACCESS",
                raise_on_failure=True,
            )
            if not message_id:
                raise RuntimeError("email provider returned no message id")
            db.commit()
        except Exception:
            db.rollback()
            raise

        _print(f"secure portal access email accepted; message_id={message_id}")


if __name__ == "__main__":
    main()
