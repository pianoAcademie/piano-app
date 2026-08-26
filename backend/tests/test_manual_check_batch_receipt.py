from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from app.api.routes.admin_clients import (
    _check_deposit_label_from_transaction,
    _send_check_received_notification_email,
)


def test_check_deposit_label_is_recovered_from_saved_transaction() -> None:
    transaction = SimpleNamespace(
        description="Cheque recu le 26/08/2026 - a deposer en février 2027",
        label="Paiement manuel",
    )

    assert _check_deposit_label_from_transaction(transaction) == "février 2027"


def test_batch_receipt_email_summarizes_every_check_once() -> None:
    client = SimpleNamespace(id=uuid4(), email="client@example.com")
    checks = [
        (Decimal("320.75"), datetime(2026, 8, 26, tzinfo=timezone.utc), "septembre 2026"),
        (Decimal("320.75"), datetime(2026, 8, 26, tzinfo=timezone.utc), "décembre 2026"),
        (Decimal("320.75"), datetime(2026, 8, 26, tzinfo=timezone.utc), "février 2027"),
        (Decimal("320.75"), datetime(2026, 8, 26, tzinfo=timezone.utc), "avril 2027"),
    ]
    rendered: dict[str, object] = {}

    def capture_email(**kwargs: object) -> str:
        rendered.update(kwargs)
        return "<html>batch receipt</html>"

    with (
        patch(
            "app.api.routes.admin_clients.resolve_billing_profile",
            return_value=SimpleNamespace(email="client@example.com", first_name="Jeanne", last_name="Hu"),
        ),
        patch(
            "app.api.routes.admin_clients.resolve_sender_profile",
            return_value=SimpleNamespace(
                from_email="contact@piano-academie.com",
                from_name="Piano Académie",
                reply_to=None,
                subject_prefix="",
            ),
        ),
        patch("app.api.routes.admin_clients.render_branded_email", side_effect=capture_email),
        patch("app.api.routes.admin_clients.send_email", return_value="message-id") as send_email,
    ):
        recipients, message_id, error = _send_check_received_notification_email(
            SimpleNamespace(),
            client=client,
            amount=checks[-1][0],
            currency="EUR",
            received_at=checks[-1][1],
            check_deposit_label=checks[-1][2],
            checks=checks,
        )

    assert recipients == ["client@example.com"]
    assert message_id == "message-id"
    assert error is None
    assert rendered["title"] == "4 chèques bien reçus"
    assert rendered["intro"] == "Nous vous confirmons la bonne réception de vos 4 chèques."
    assert rendered["rows"] == [
        ("Chèque 1", "320,75 € · reçu le 26/08/2026 · dépôt prévu en septembre 2026"),
        ("Chèque 2", "320,75 € · reçu le 26/08/2026 · dépôt prévu en décembre 2026"),
        ("Chèque 3", "320,75 € · reçu le 26/08/2026 · dépôt prévu en février 2027"),
        ("Chèque 4", "320,75 € · reçu le 26/08/2026 · dépôt prévu en avril 2027"),
        ("Montant total reçu", "1283,00 €"),
    ]
    assert send_email.call_count == 1
    assert send_email.call_args.kwargs["subject"] == "Réception de vos 4 chèques - Jeanne Hu"
