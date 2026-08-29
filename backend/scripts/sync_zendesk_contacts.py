from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.db.session import SessionLocal
from app.services.notifications.domain.constants import SOURCE_ADMIN_BO
from app.services.zendesk_contact_sync import DEFAULT_LIMIT, run_zendesk_contact_sync_job


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Synchronise les adultes/responsables et prospects vers Zendesk.")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Applique réellement les créations/mises à jour. Sans ce drapeau, aucune écriture Zendesk.",
    )
    parser.add_argument("--full", action="store_true", help="Ignore le curseur et contrôle toute la base.")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="Nombre maximal de contacts à traiter.")
    parser.add_argument(
        "--check-connection",
        action="store_true",
        help="Vérifie en lecture seule que les identifiants Zendesk fonctionnent.",
    )
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    if args.limit < 1 or args.limit > 10_000:
        print("[ERROR] --limit doit être compris entre 1 et 10000.", file=sys.stderr)
        return 2

    db = SessionLocal()
    try:
        result = run_zendesk_contact_sync_job(
            db,
            now=datetime.now(UTC),
            limit=args.limit,
            dry_run=not args.apply,
            full=args.full,
            check_connection=args.check_connection,
            triggered_by=SOURCE_ADMIN_BO,
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        print(f"[ERROR] Synchronisation Zendesk impossible : {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()

    mode = "CONTROLE A BLANC" if result.dry_run else "APPLICATION"
    print(
        f"[OK] {mode} - analysés={result.checked}, synchronisés={result.created_or_updated}, "
        f"échecs={result.failed}, numéros_partagés={result.conflicts}, "
        f"fiches_talk_fusionnées={result.talk_callers_merged}, "
        f"numéros_à_vérifier={result.unresolved_phone_owners}"
    )
    return 0 if result.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
