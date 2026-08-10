from __future__ import annotations

import unittest

from app.services.email_branding import render_branded_email


class EmailBrandingTests(unittest.TestCase):
    def test_renderer_escapes_customer_values_and_keeps_valid_links(self) -> None:
        body = render_branded_email(
            preview="Paiement reçu",
            eyebrow="PAIEMENT",
            title="Paiement confirmé",
            greeting="Bonjour <Client>,",
            intro="Votre paiement a été reçu.",
            rows=[("Montant", "20,00 € <ok>")],
            button_url="https://app.piano-academie.com/client",
            button_label="Ouvrir mon espace",
            links=[("Facture", "https://app.piano-academie.com/facture")],
        )

        self.assertTrue(body.startswith("<!doctype html>"))
        self.assertIn("PIANO ACADÉMIE", body)
        self.assertIn("Bonjour &lt;Client&gt;", body)
        self.assertIn("20,00 € &lt;ok&gt;", body)
        self.assertIn('href="https://app.piano-academie.com/client"', body)
        self.assertIn('href="https://app.piano-academie.com/facture"', body)

    def test_renderer_accepts_template_placeholder_urls_but_rejects_unsafe_urls(self) -> None:
        placeholder_body = render_branded_email(
            preview="Accès",
            eyebrow="COMPTE",
            title="Accès sécurisé",
            greeting="Bonjour,",
            intro="Votre accès est prêt.",
            button_url="{reset_url}",
            button_label="Choisir mon mot de passe",
        )
        unsafe_body = render_branded_email(
            preview="Accès",
            eyebrow="COMPTE",
            title="Accès sécurisé",
            greeting="Bonjour,",
            intro="Votre accès est prêt.",
            button_url="javascript:alert(1)",
            button_label="Ouvrir",
        )

        self.assertIn('href="{reset_url}"', placeholder_body)
        self.assertNotIn("javascript:", unsafe_body)


if __name__ == "__main__":
    unittest.main()
