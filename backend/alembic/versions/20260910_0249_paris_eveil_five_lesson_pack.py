"""Configure Paris musical awakening as a five-lesson pack.

Revision ID: 20260910_0249
Revises: 20260907_0248
"""

import json

from alembic import op
import sqlalchemy as sa


revision = "20260910_0249"
down_revision = "20260907_0248"
branch_labels = None
depends_on = None


ACTIVITY_CODE = "ACT_EVEIL_MUSICAL_98E099"
PARIS_FORM_SOURCES = (
    "typeform_paris_eveil_2026_2027_multisite",
    "REAL_2026_PARIS_INITIATION_EXISTING_CATALOG",
)

FR_PACK_SUMMARY = (
    '<p>&lt;div style="margin:18px 0; padding:16px; border:1px solid #d6a23d; background:#fff8e8;"&gt;</p>'
    '<p>&lt;strong&gt;Formule Éveil musical Paris : carnet de 5 cours d’une heure&lt;/strong&gt;</p>'
    '<p>32 € TTC par cours, soit 160 € TTC le carnet. Sans engagement annuel et sans concert de fin d’année.</p>'
    '<p>Une séance annulée au moins 24 heures à l’avance peut être reportée sur un autre créneau disponible.</p>'
    '<p>&lt;/div&gt;</p>'
)

EN_PACK_SUMMARY = (
    '<div style="margin:18px 0; padding:16px; border:1px solid #d6a23d; background:#fff8e8;">'
    '<p><strong>Paris Early Music Discovery: pack of five one-hour lessons</strong></p>'
    '<p>€32 including VAT per lesson, i.e. €160 including VAT for the pack. No annual commitment and no end-of-year concert.</p>'
    '<p>A lesson cancelled at least 24 hours in advance may be rescheduled to another available time slot.</p>'
    '</div>'
)

FR_TERMS = """<p><strong>CONDITIONS D’INSCRIPTION – ÉVEIL MUSICAL À PARIS – CARNET DE 5 COURS – 2026 / 2027</strong></p>
<p>Afin de finaliser l’inscription de votre enfant, nous vous invitons à lire attentivement les conditions suivantes. La validation du devis emporte acceptation de ces conditions.</p>
<p><strong>1. Formule et calendrier</strong></p>
<p>L’inscription porte sur un carnet de cinq cours collectifs d’éveil musical d’une heure, à utiliser sur les créneaux proposés par Piano Académie à Paris selon le calendrier indiqué sur le devis et le portail famille.</p>
<p>Cette formule ne comporte aucun engagement annuel. Une fois les cinq cours utilisés, la famille peut acheter un nouveau carnet, sous réserve des places disponibles.</p>
<p>Les cours sont suspendus pendant les vacances scolaires de la zone C, les jours fériés et les fermetures annoncées par l’école. Un rappel est envoyé avant chaque cours confirmé.</p>
<p><strong>2. Tarif et règlement</strong></p>
<p>Le tarif est de 32 € TTC par cours d’une heure. Le carnet de cinq cours est donc facturé 160 € TTC et réglé à l’avance.</p>
<p>Le carnet est personnel, non cessible et non remboursable, sous réserve du droit de rétractation applicable, d’un cas de force majeure ou d’une décision exceptionnelle de l’école.</p>
<p>Le paiement s’effectue par carte bancaire, virement bancaire ou chèque. Les espèces ne sont pas acceptées. En cas de retard de paiement, Piano Académie peut suspendre l’accès aux cours jusqu’à régularisation.</p>
<p><strong>3. Annulation et rattrapage</strong></p>
<p>La famille peut annuler un cours à condition de prévenir Piano Académie au moins 24 heures avant l’heure prévue. La séance n’est alors pas décomptée du carnet et peut être rattrapée sur un autre créneau d’éveil musical à Paris, sous réserve des places disponibles.</p>
<p>Toute annulation reçue moins de 24 heures avant le cours, ainsi que toute absence non signalée, entraîne le décompte de la séance ; elle ne donne lieu ni à remboursement ni à rattrapage.</p>
<p>Lorsqu’un cours est annulé par Piano Académie, la séance n’est pas décomptée et une solution de report est proposée.</p>
<p><strong>4. Organisation pédagogique</strong></p>
<p>Le professeur est désigné par Piano Académie. L’école peut modifier cette affectation ou assurer un remplacement ponctuel afin de garantir la continuité pédagogique.</p>
<p>L’assiduité et le respect du groupe sont nécessaires. En cas de comportement perturbant de manière répétée le cours, l’école peut restreindre ou suspendre l’accès de l’enfant aux séances.</p>
<p><strong>5. Absence de concert de fin d’année</strong></p>
<p>La formule d’éveil musical en carnet de cinq cours ne comprend pas de concert de fin d’année ni de frais de participation à un concert.</p>
<p><strong>6. Situations exceptionnelles</strong></p>
<p>En cas de fermeture administrative, d’indisponibilité des locaux ou de circonstance exceptionnelle, l’école peut proposer un report, une séance à distance ou une solution pédagogique équivalente. Une séance annulée par l’école n’est pas perdue.</p>
<p>Tout enfant dont l’état de santé est incompatible avec la participation au cours ne pourra être accueilli. Les règles d’annulation prévues à l’article 3 restent applicables.</p>
<p><strong>7. Communication avec l’école</strong></p>
<p>Les échanges doivent se faire par email ou via le portail famille. Tout changement de coordonnées doit être signalé rapidement.</p>
<p>Administration : <a href="mailto:administration@piano-academie.com">administration@piano-academie.com</a><br>Comptabilité : <a href="mailto:comptabilite@piano-academie.com">comptabilite@piano-academie.com</a></p>
<p><strong>8. Lieux des cours</strong></p>
<p>Les cours d’éveil musical concernés sont organisés à Paris, sur les sites et créneaux indiqués dans le devis et le portail famille.</p>
<p>Les parents ne peuvent assister aux cours sauf autorisation exceptionnelle. L’école ne peut être tenue responsable des pertes, vols ou dégradations d’objets personnels.</p>
<p><strong>9. Droit à l’image et données personnelles</strong></p>
<p>L’école peut utiliser l’image des élèves à des fins de communication. En cas d’opposition, la famille peut écrire à administration@piano-academie.com. Les données personnelles sont traitées conformément à la réglementation applicable.</p>
<p><strong>10. Droit de rétractation et validation</strong></p>
<p>Conformément à l’article L221-18 du Code de la consommation, une inscription conclue à distance bénéficie d’un délai de rétractation de 14 jours. Si l’exécution commence avant l’expiration de ce délai à la demande expresse de la famille, le montant correspondant aux prestations déjà réalisées reste dû.</p>
<p>La validation du devis par clic sur le bouton « Approuver » vaut signature électronique au sens de l’article 1367 du Code civil et engage le signataire.</p>"""

EN_TERMS = """<p><strong>ENROLMENT TERMS – EARLY MUSIC DISCOVERY IN PARIS – FIVE-LESSON PACK – 2026 / 2027</strong></p>
<p>To finalise your child's enrolment, please read these terms carefully. Approving the quote means accepting these terms.</p>
<p><strong>1. Package and schedule</strong></p>
<p>Enrolment is for a pack of five one-hour group Early Music Discovery lessons, to be used in the Paris time slots offered by Piano Académie according to the quote and family portal.</p>
<p>There is no annual commitment. After all five lessons have been used, the family may purchase another pack, subject to availability.</p>
<p>Lessons are suspended during Zone C school holidays, French public holidays and announced school closures. A reminder is sent before each confirmed lesson.</p>
<p><strong>2. Price and payment</strong></p>
<p>The price is €32 including VAT per one-hour lesson. The five-lesson pack therefore costs €160 including VAT and is paid in advance.</p>
<p>The pack is personal, non-transferable and non-refundable, subject to statutory withdrawal rights, force majeure or an exceptional decision by the school.</p>
<p>Payment may be made by bank card, bank transfer or cheque. Cash is not accepted. Piano Académie may suspend access to lessons while an overdue payment remains outstanding.</p>
<p><strong>3. Cancellation and make-up lessons</strong></p>
<p>A family may cancel a lesson by notifying Piano Académie at least 24 hours before its scheduled start. The lesson is then not deducted from the pack and may be made up in another available Paris Early Music Discovery time slot, subject to capacity.</p>
<p>A cancellation received less than 24 hours before the lesson, or a no-show, counts as a used lesson and cannot be refunded or made up.</p>
<p>If Piano Académie cancels a lesson, it is not deducted and an alternative will be offered.</p>
<p><strong>4. Teaching arrangements</strong></p>
<p>The teacher is appointed by Piano Académie. The school may change the teacher or arrange a substitute to ensure teaching continuity.</p>
<p>Regular attendance and respectful group behaviour are required. Repeatedly disruptive behaviour may result in restricted or suspended access to lessons.</p>
<p><strong>5. No end-of-year concert</strong></p>
<p>The five-lesson Early Music Discovery pack does not include an end-of-year concert or any concert participation fee.</p>
<p><strong>6. Exceptional circumstances</strong></p>
<p>If premises are unavailable or exceptional circumstances arise, the school may offer a rescheduled lesson, an online lesson or an equivalent teaching solution. A lesson cancelled by the school is not lost.</p>
<p>A child whose health is incompatible with taking part cannot attend. The cancellation rules in section 3 continue to apply.</p>
<p><strong>7. Communication</strong></p>
<p>Communications must be made by email or through the family portal. Changes to contact details must be reported promptly.</p>
<p>Administration: <a href="mailto:administration@piano-academie.com">administration@piano-academie.com</a><br>Accounts: <a href="mailto:comptabilite@piano-academie.com">comptabilite@piano-academie.com</a></p>
<p><strong>8. Lesson locations</strong></p>
<p>These lessons take place in Paris at the locations and times shown in the quote and family portal.</p>
<p>Parents may not attend lessons unless exceptionally authorised. The school is not responsible for lost, stolen or damaged personal items.</p>
<p><strong>9. Image and personal data</strong></p>
<p>The school may use student images for communications. Families may object by emailing administration@piano-academie.com. Personal data is processed in accordance with applicable law.</p>
<p><strong>10. Withdrawal and approval</strong></p>
<p>Under Article L221-18 of the French Consumer Code, a distance enrolment has a 14-day withdrawal period. If performance begins earlier at the family's express request, payment remains due for services already provided.</p>
<p>Approving the quote electronically constitutes an electronic signature and binds the signatory to these terms.</p>"""


def _create_quote_version(connection: sa.Connection, code: str, summary: str, marker: str) -> object:
    row = connection.execute(
        sa.text("""
            SELECT q.id, q.current_version_id, v.version_number, v.content_snapshot
            FROM quote_templates q
            JOIN quote_template_versions v ON v.id = q.current_version_id
            WHERE q.code = :code
            FOR UPDATE OF q
        """),
        {"code": code},
    ).mappings().one()
    content = dict(row["content_snapshot"] or {})
    body = str(content.get("body_template") or "")
    if marker not in body:
        raise RuntimeError(f"Expected insertion marker missing from {code}")
    content["body_template"] = body.replace(marker, summary + marker, 1)
    connection.execute(
        sa.text("UPDATE quote_template_versions SET is_active_version = false, updated_at = now() WHERE quote_template_id = :id"),
        {"id": row["id"]},
    )
    version_id = connection.execute(
        sa.text("""
            INSERT INTO quote_template_versions (
                quote_template_id, version_number, content_snapshot,
                is_active_version, published_at, changelog, created_at, updated_at
            ) VALUES (
                :template_id, :version_number, CAST(:content AS jsonb),
                true, now(), :changelog, now(), now()
            ) RETURNING id
        """),
        {
            "template_id": row["id"],
            "version_number": connection.execute(
                sa.text("SELECT COALESCE(MAX(version_number), 0) + 1 FROM quote_template_versions WHERE quote_template_id = :id"),
                {"id": row["id"]},
            ).scalar_one(),
            "content": json.dumps(content, ensure_ascii=False),
            "changelog": "Paris musical awakening: five lessons at EUR 32, 24-hour cancellation, no annual commitment or concert.",
        },
    ).scalar_one()
    connection.execute(
        sa.text("UPDATE quote_templates SET current_version_id = :version_id, updated_at = now() WHERE id = :id"),
        {"version_id": version_id, "id": row["id"]},
    )
    return version_id


def _create_terms_version(connection: sa.Connection, code: str, html: str, version_label: str) -> object:
    row = connection.execute(
        sa.text("""
            SELECT t.id, v.version_number, v.content_snapshot
            FROM terms_templates t
            JOIN terms_template_versions v ON v.id = t.current_version_id
            WHERE t.code = :code
            FOR UPDATE OF t
        """),
        {"code": code},
    ).mappings().one()
    content = dict(row["content_snapshot"] or {})
    content["content"] = html
    content["version_label"] = version_label
    connection.execute(
        sa.text("UPDATE terms_template_versions SET is_active_version = false, updated_at = now() WHERE terms_template_id = :id"),
        {"id": row["id"]},
    )
    version_id = connection.execute(
        sa.text("""
            INSERT INTO terms_template_versions (
                terms_template_id, version_number, content_snapshot,
                is_active_version, published_at, changelog, created_at, updated_at
            ) VALUES (
                :template_id, :version_number, CAST(:content AS jsonb),
                true, now(), :changelog, now(), now()
            ) RETURNING id
        """),
        {
            "template_id": row["id"],
            "version_number": connection.execute(
                sa.text("SELECT COALESCE(MAX(version_number), 0) + 1 FROM terms_template_versions WHERE terms_template_id = :id"),
                {"id": row["id"]},
            ).scalar_one(),
            "content": json.dumps(content, ensure_ascii=False),
            "changelog": "Paris musical awakening: five-lesson pack terms.",
        },
    ).scalar_one()
    connection.execute(
        sa.text("UPDATE terms_templates SET current_version_id = :version_id, updated_at = now() WHERE id = :id"),
        {"version_id": version_id, "id": row["id"]},
    )
    return version_id


def upgrade() -> None:
    connection = op.get_bind()

    fr_quote_version = _create_quote_version(
        connection,
        "TEMPLATE_EVEIL_MUSICAL",
        FR_PACK_SUMMARY,
        '<p>&lt;h2&gt;Le tarif de nos prestations&lt;/h2&gt;</p>',
    )
    en_quote_version = _create_quote_version(
        connection,
        "TEMPLATE_EVEIL_MUSICAL_EN",
        EN_PACK_SUMMARY,
        '<p>{services_table_html}</p>',
    )
    fr_terms_version = _create_terms_version(
        connection,
        "CGV_EVEIL_MUSICAL_PARIS",
        FR_TERMS,
        "CGV - Éveil musical Paris - Carnet 5 cours - V2.0",
    )
    en_terms_version = _create_terms_version(
        connection,
        "CGV_EVEIL_MUSICAL_PARIS_EN",
        EN_TERMS,
        "Terms - Paris Early Music Discovery - Five-lesson pack - V2.0",
    )

    connection.execute(
        sa.text("""
            UPDATE quote_document_bindings b
            SET quote_template_version_id = CASE
                    WHEN b.language = 'en' THEN :en_quote_version
                    ELSE :fr_quote_version
                END,
                terms_template_version_id = CASE
                    WHEN b.language = 'en' THEN :en_terms_version
                    ELSE :fr_terms_version
                END,
                updated_at = now()
            FROM course_types ct
            WHERE b.activity_id = ct.id
              AND ct.code = :activity_code
              AND b.is_active = true
        """),
        {
            "activity_code": ACTIVITY_CODE,
            "fr_quote_version": fr_quote_version,
            "en_quote_version": en_quote_version,
            "fr_terms_version": fr_terms_version,
            "en_terms_version": en_terms_version,
        },
    )

    form_rows = connection.execute(
        sa.text("""
            SELECT id, configuration_json
            FROM typeform_form_configs
            WHERE source_code = ANY(:source_codes)
              AND is_active = true
            FOR UPDATE
        """),
        {"source_codes": list(PARIS_FORM_SOURCES)},
    ).mappings().all()
    if len(form_rows) != len(PARIS_FORM_SOURCES):
        raise RuntimeError("Expected active Paris musical awakening form configurations are missing")
    for row in form_rows:
        config = dict(row["configuration_json"] or {})
        changed = False
        line_templates = []
        for raw_template in config.get("line_templates") or []:
            template = dict(raw_template)
            if template.get("activity_code") == ACTIVITY_CODE:
                template.update(
                    {
                        "quantity": "5",
                        "unit_price_ttc": "32.00",
                        "allow_price_override": True,
                        "price_mode": "override",
                        "planning_session_limit": 5,
                        "commitment_kind": "PACK_5",
                    }
                )
                changed = True
            line_templates.append(template)
        if not changed:
            raise RuntimeError("Paris form does not contain the expected musical awakening line")
        config["line_templates"] = line_templates
        connection.execute(
            sa.text("UPDATE typeform_form_configs SET configuration_json = CAST(:config AS jsonb), updated_at = now() WHERE id = :id"),
            {"config": json.dumps(config, ensure_ascii=False), "id": row["id"]},
        )

    result = connection.execute(
        sa.text("""
            UPDATE pricing_activity_prices pap
            SET is_active = false, updated_at = now()
            FROM pricing_catalogs pc, course_types ct
            WHERE pap.catalog_id = pc.id
              AND pap.activity_id = ct.id
              AND pc.school_year_label = '2026-2027'
              AND pc.lifecycle_status = 'PUBLISHED'
              AND ct.code = :activity_code
              AND pap.price_channel = 'ANNUAL_FORFAIT'
              AND pap.unit_price_ttc = 22.00
              AND pap.is_active = true
        """),
        {"activity_code": ACTIVITY_CODE},
    )
    if result.rowcount != 1:
        raise RuntimeError("Expected one active EUR 22 annual price for Paris musical awakening")


def downgrade() -> None:
    connection = op.get_bind()
    for table, version_table, foreign_key, codes in (
        ("quote_templates", "quote_template_versions", "quote_template_id", ("TEMPLATE_EVEIL_MUSICAL", "TEMPLATE_EVEIL_MUSICAL_EN")),
        ("terms_templates", "terms_template_versions", "terms_template_id", ("CGV_EVEIL_MUSICAL_PARIS", "CGV_EVEIL_MUSICAL_PARIS_EN")),
    ):
        for code in codes:
            row = connection.execute(
                sa.text(f"""
                    SELECT t.id, t.current_version_id, v.version_number
                    FROM {table} t
                    JOIN {version_table} v ON v.id = t.current_version_id
                    WHERE t.code = :code
                    FOR UPDATE OF t
                """),
                {"code": code},
            ).mappings().one()
            previous_id = connection.execute(
                sa.text(f"SELECT id FROM {version_table} WHERE {foreign_key} = :id AND version_number = :number"),
                {"id": row["id"], "number": int(row["version_number"]) - 1},
            ).scalar_one()
            connection.execute(sa.text(f"UPDATE {version_table} SET is_active_version = (id = :previous_id) WHERE {foreign_key} = :id"), {"previous_id": previous_id, "id": row["id"]})
            connection.execute(sa.text(f"UPDATE {table} SET current_version_id = :previous_id, updated_at = now() WHERE id = :id"), {"previous_id": previous_id, "id": row["id"]})

    form_rows = connection.execute(
        sa.text("SELECT id, configuration_json FROM typeform_form_configs WHERE source_code = ANY(:source_codes) FOR UPDATE"),
        {"source_codes": list(PARIS_FORM_SOURCES)},
    ).mappings().all()
    for row in form_rows:
        config = dict(row["configuration_json"] or {})
        templates = []
        for raw_template in config.get("line_templates") or []:
            template = dict(raw_template)
            if template.get("activity_code") == ACTIVITY_CODE:
                template["quantity"] = "1"
                for key in ("unit_price_ttc", "allow_price_override", "price_mode", "planning_session_limit", "commitment_kind"):
                    template.pop(key, None)
            templates.append(template)
        config["line_templates"] = templates
        connection.execute(
            sa.text("UPDATE typeform_form_configs SET configuration_json = CAST(:config AS jsonb), updated_at = now() WHERE id = :id"),
            {"config": json.dumps(config, ensure_ascii=False), "id": row["id"]},
        )

    connection.execute(
        sa.text("""
            UPDATE pricing_activity_prices pap
            SET is_active = true, updated_at = now()
            FROM pricing_catalogs pc, course_types ct
            WHERE pap.catalog_id = pc.id
              AND pap.activity_id = ct.id
              AND pc.school_year_label = '2026-2027'
              AND ct.code = :activity_code
              AND pap.price_channel = 'ANNUAL_FORFAIT'
              AND pap.unit_price_ttc = 22.00
        """),
        {"activity_code": ACTIVITY_CODE},
    )

    connection.execute(
        sa.text("""
            UPDATE quote_document_bindings b
            SET quote_template_version_id = q.current_version_id,
                terms_template_version_id = t.current_version_id,
                updated_at = now()
            FROM course_types ct, quote_templates q, terms_templates t
            WHERE b.activity_id = ct.id
              AND ct.code = :activity_code
              AND q.id = b.quote_template_id
              AND t.id = b.terms_template_id
        """),
        {"activity_code": ACTIVITY_CODE},
    )
