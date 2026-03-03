# Documentation - migration multi-entites facturation

## Journal des decisions
- Source de verite legal entity: `legal_entities` (DB).
- Compatibilite legacy maintenue temporairement:
  - anciennes colonnes texte conservees,
  - fallback `app_settings` pour PDF uniquement si `legal_entity_id` absent.
- Les cles legacy `config_account_services_*` restent lues uniquement en fallback PDF historique (si `legal_entity_id` absent) et restent optionnelles.
- Suppression du mapping hardcode Academie/Services dans le rendu facture.
- Derivation `billing_entity` cote API via `seller_legal_entity_id -> legal_entities.name` (fallback texte legacy seulement si FK absente).
- Validation minimale ajoutee pour les legal entities: `name` + `country_code` + `invoice_prefix` requis.
- PSP ajoute: `STRIPE` (en plus de `PAYPLUG`, `MOLLIE`).
- Chaque `legal_entity` porte desormais un `default_payment_provider` configure depuis le BO.

## Modifications principales
- Migration Alembic:
  - creation de `legal_entities`
  - ajout des FK nullable sur `course_types`, `course_sessions`, `client_invoice_lines`
  - seed 2 entites historiques
  - backfill des FK depuis colonnes legacy
- Modeles SQLAlchemy:
  - ajout `LegalEntity`
  - ajout `LegalEntity.default_payment_provider`
  - ajout des colonnes `seller_legal_entity_id` / `snapshot_seller_legal_entity_id`
- PSP:
  - endpoint `/api/v1/admin/config/payment-provider` et UI BO etendus avec cles Stripe (`sk_test_` / `sk_live_`)
  - support checkout/lookup Stripe dans `payment_checkout.py`
  - resolution provider sur reference paiement (`cs_...` => Stripe) pour la confirmation/webhook
- Pipeline facture:
  - snapshot FK sur session
  - persistance FK sur lignes de facture
  - rendu PDF base sur `legal_entity_id`
- Endpoints admin/client:
  - sortie `seller_legal_entity_id`
  - `billing_entity` derive de l'entite legale DB
- Numerotation facture:
  - nouveau service `InvoiceNumberService.allocate_invoice_number(...)`
  - allocation atomique via `SELECT ... FOR UPDATE` sur `legal_entities`
  - sequence par entite (`invoice_prefix` + `invoice_next_number`) au lieu du compteur global
  - split facture: chaque note/facture creee recoit un numero reel propre (sans suffixes)

## Comment tester
1. Rebuild backend
- `COMPOSE_PROJECT_NAME=piano-app docker compose up -d --build backend`

2. Appliquer les migrations
- `COMPOSE_PROJECT_NAME=piano-app docker compose exec -T backend alembic upgrade head`

3. Verifier backfill FK
- `COMPOSE_PROJECT_NAME=piano-app docker compose exec -T db psql -U piano -d piano_academie -c "SELECT (SELECT COUNT(*) FROM legal_entities) AS legal_entities, (SELECT COUNT(*) FROM course_types WHERE seller_legal_entity_id IS NULL) AS course_types_null, (SELECT COUNT(*) FROM course_sessions WHERE snapshot_seller_legal_entity_id IS NULL) AS course_sessions_null, (SELECT COUNT(*) FROM client_invoice_lines WHERE seller_legal_entity_id IS NULL) AS invoice_lines_null;"`

4. Smoke backend
- `COMPOSE_PROJECT_NAME=piano-app docker compose exec -T backend python scripts/smoke_v1.py`

5. Build frontend
- `COMPOSE_PROJECT_NAME=piano-app docker compose exec -T frontend npm run build`

6. Export annuel SAP (cours a domicile, Services)
- Endpoint: `GET /api/v1/admin/reports/sap/{year}/csv`
- Exemple:
  - `curl -H "Authorization: Bearer <ADMIN_JWT>" "http://localhost:8000/api/v1/admin/reports/sap/2026/csv" -o sap_services_2026.csv`
- Smoke dedie:
  - `COMPOSE_PROJECT_NAME=piano-app docker compose exec -T backend python /app/scripts/smoke_sap_export_v1.py`

7. Smoke config PSP + entites
- `COMPOSE_PROJECT_NAME=piano-app docker compose exec -T backend python /app/scripts/smoke_config_v1.py`
- Ce smoke verifie aussi:
  - update provider global en `STRIPE`
  - update d'une legal entity avec `default_payment_provider=STRIPE`

## Etat de verification actuel
- `alembic upgrade head`: OK
- `smoke_v1.py`: OK
- `npm run build`: OK
- `npm run lint` frontend: script absent dans ce projet (non executable)
- `pytest` backend: non disponible dans l'image (`No module named pytest`)
