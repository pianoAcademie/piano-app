from __future__ import annotations

import secrets
import string

from app.services.email_delivery import send_email


def generate_temporary_password(length: int = 14) -> str:
    alphabet = string.ascii_letters + string.digits
    core = "".join(secrets.choice(alphabet) for _ in range(max(8, length - 2)))
    return f"{core}A!"


def send_professor_activation_email(*, to_email: str, full_name: str, temporary_password: str) -> str:
    subject = "Activation de votre compte professeur Piano Academie"
    body = (
        f"Bonjour {full_name},\n\n"
        "Votre compte professeur est active.\n"
        f"Identifiant: {to_email}\n"
        f"Mot de passe temporaire: {temporary_password}\n"
        "Merci de vous connecter puis de changer ce mot de passe.\n\n"
        "Piano Academie"
    )

    return send_email(
        to_email=to_email,
        subject=subject,
        body=body,
        body_format="TEXT",
        context="PROFESSOR_ACTIVATION",
    )
