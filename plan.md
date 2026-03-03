# Plan de migration multi-entites (5 etapes)

## Etape 1 - Introduire le socle DB legal_entities
- Ajouter une table `legal_entities` (identite legale + prefix + compteur de numerotation).
- Ajouter les colonnes FK nullable:
  - `course_types.seller_legal_entity_id`
  - `course_sessions.snapshot_seller_legal_entity_id`
  - `client_invoice_lines.seller_legal_entity_id`
- Impacts fichiers:
  - `backend/alembic/versions/20260306_0053_legal_entities_and_seller_fks.py`
  - `backend/app/models/ops.py`
  - `backend/app/models/catalog.py`
  - `backend/app/models/client_record.py`
  - `backend/app/models/__init__.py`

## Etape 2 - Seeder et backfiller les references
- Seeder `PIANO ACADEMIE` et `PIANO ACADEMIE SERVICES` dans `legal_entities`.
- Mapper les anciens codes texte vers FK (`billing_entity_code`, `billing_entity_snapshot`, `billing_entity`).
- Laisser les colonnes texte en place pendant la phase de transition.
- Impacts fichiers:
  - `backend/alembic/versions/20260306_0053_legal_entities_and_seller_fks.py`

## Etape 3 - Propager le snapshot legal_entity dans le pipeline
- Lors de la creation/mise a jour des sessions, snapshotter `course_type.seller_legal_entity_id` vers `course_sessions.snapshot_seller_legal_entity_id`.
- Au gel de facture, persister `seller_legal_entity_id` sur `client_invoice_lines`.
- Impacts fichiers:
  - `backend/app/api/routes/admin.py`
  - `backend/app/api/routes/admin_clients.py`
  - `backend/app/schemas/admin.py`
  - `backend/app/schemas/user.py`

## Etape 4 - Refactor rendu facture et APIs de lecture
- Rendu PDF/texte: identite emettrice resolue via `legal_entities.id`; fallback legacy `app_settings` uniquement si `legal_entity_id` absent.
- Endpoints clients/admin: `billing_entity` derive de `legal_entity.name` (via `seller_legal_entity_id`), sans normalisation forcee sur `PIANO_ACADEMIE`.
- Impacts fichiers:
  - `backend/app/services/invoice_documents.py`
  - `backend/app/api/routes/clients.py`
  - `backend/app/api/routes/admin_clients.py`

## Etape 5 - Durcissement progressif et decommission legacy
- Ajouter des gardes applicatives pour imposer le FK sur nouvelles ecritures.
- Superviser les compteurs `NULL` FK; passer en `NOT NULL` SQL quand donnees stabilisees.
- Supprimer ensuite les colonnes texte legacy sur une release dediee.
- Impacts fichiers:
  - Alembic(s) futures de contrainte
  - BO CRUD legal entities (a finaliser)
  - Nettoyage API/models legacy (a planifier)
