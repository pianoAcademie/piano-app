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
- Transactions manuelles:
  - ajout `client_manual_transactions.legal_entity_id` (FK `legal_entities`)
  - derivation de l'entite depuis factures rapprochees si selectionnees
  - fallback sur mode de paiement (virement/cheque/especes) via mapping BO
  - entite obligatoire pour nouvelles transactions quand non derivable
  - blocage explicite si rapprochement inter-entites: `Créer un paiement par entité`
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

8. Smoke transactions multi-entites (paiements/avoirs/rabais)
- `COMPOSE_PROJECT_NAME=piano-app docker compose exec -T backend python scripts/smoke_transactions_legal_entities_v1.py`
- Verifie:
  - paiement manuel sans facture: entite obligatoire
  - rapprochement sur 2 factures meme entite: OK
  - rapprochement sur factures entites differentes: erreur `Créer un paiement par entité`

## Etat de verification actuel
- `alembic upgrade head`: OK
- `smoke_v1.py`: OK
- `npm run build`: OK
- `npm run lint` frontend: script absent dans ce projet (non executable)
- `pytest` backend: non disponible dans l'image (`No module named pytest`)

## Workflow professeurs/collaborateurs multi-entites (PR1 -> PR6)

### Endpoints backend ajoutes
- BO collaborateurs:
  - `PATCH /api/v1/admin/collaborators/{id}`
  - `POST /api/v1/admin/collaborators/{id}/send-password`
- Modele facture professeur:
  - `GET /api/v1/admin/teacher-invoice-template`
  - `PUT /api/v1/admin/teacher-invoice-template`
  - `POST /api/v1/admin/teacher-invoice-template/preview`
- Portail professeur:
  - `GET /api/v1/teacher/statements?year=&month=`
  - `GET /api/v1/teacher/statements/{year}/{month}`
  - `POST /api/v1/teacher/statements/{year}/{month}/approve`
  - `POST /api/v1/teacher/statements/{year}/{month}/dispute`
  - `GET /api/v1/teacher/invoices?year=&month=`
  - `GET /api/v1/teacher/invoices/{invoice_id}`
  - `GET /api/v1/teacher/invoices/{invoice_id}/pdf`
  - `POST /api/v1/teacher/invoices/{invoice_id}/cancel`
  - `POST /api/v1/teacher/invoices/{invoice_id}/uncancel`
  - `POST /api/v1/teacher/invoices/{invoice_id}/send-to-accounting`

### Notes securite reset password
- Aucun mot de passe n'est stocke ni envoye en clair.
- `POST /api/v1/admin/collaborators/{id}/send-password` genere un token one-time hashé avec expiration 24h.
- Le lien de reset passe par `POST /api/v1/auth/reset-password`:
  - token compare par hash,
  - token marque `used_at`,
  - les autres tokens actifs du meme user sont invalidés.

### Multi-entites cote prof
- Le payeur est `course_types.payor_legal_entity_id` (FK `legal_entities`), editable en BO.
- Snapshot de payeur sur seance: `course_sessions.snapshot_payor_legal_entity_id`.
- Releve/approbation groupe par `(teacher_id, payor_legal_entity_id, year, month)`.
- Generation: 1 facture professeur par statement payeur.
- Compteur facture professeur global `professors.teacher_invoice_counter` avec lock transactionnel.

### Commandes de validation executees
- `COMPOSE_PROJECT_NAME=piano-app docker compose exec -T backend alembic upgrade head`
- `COMPOSE_PROJECT_NAME=piano-app docker compose exec -T backend python scripts/smoke_v1.py`
- `COMPOSE_PROJECT_NAME=piano-app docker compose exec -T backend python scripts/smoke_billing_entities_v1.py`
- `COMPOSE_PROJECT_NAME=piano-app docker compose exec -T backend python scripts/smoke_teacher_invoicing_v1.py`
- `COMPOSE_PROJECT_NAME=piano-app docker compose exec -T frontend npm run build`

## Reporting communications (pagination + periodes + archivage)

### Endpoint admin
- `GET /api/v1/admin/reports/communications`
- Parametres:
  - `channel`: `EMAIL` | `SMS` (optionnel; absent => tous)
  - `period`: `TODAY` | `WEEK` | `MONTH` | `SEMESTER` | `YEAR` | `ALL` (defaut `TODAY`)
  - `page`: index 1-based (defaut `1`)
  - `per_page`: `25` | `50` | `100` (defaut `50`)
  - `q`, `communication_type`, `professor_id` (filtres existants)
- Reponse:
  - `{ items, page, per_page, total, total_pages }`

### Regle d archivage
- Les messages de plus d un an sont marques archives (`communication_logs.archived_at`) automatiquement.
- Le filtre `ALL` permet l affichage depuis origine.

### UI BO
- Page `/admin/communications`:
  - pagination avec 25/50/100 (defaut 50),
  - filtre periode (defaut jour),
  - colonne `Canal` (Email/SMS).

## Planning mois + navigation admin (UI premium)

### Payload planning enrichi (backend)
- Endpoint: `GET /api/v1/admin/sessions`
- Champs ajoutes par evenement:
  - `teacher_id`
  - `teacher_display_name`
  - `location_label`
  - `type_label`
  - `status_label`
- Requete backend en `JOIN` (`course_sessions` + `course_types` + `locations` + `professors`) pour eviter le N+1.

### Composants frontend
- `frontend/components/planning/month-day-card.tsx`
- `frontend/components/planning/month-event-chip.tsx`
- `frontend/components/planning/day-events-drawer.tsx`

### Mini smoke UI manuel
1. Ouvrir `/admin` en vue planning mois.
2. Verifier qu'un evenement affiche le professeur sans clic (`Prof : ...`) sur chaque chip.
3. Verifier qu'un jour avec >3 cours affiche `+N autres` et ouvre le drawer de detail.
4. Verifier que la topbar n'affiche plus la liste des modules, et que la sidebar est sectionnee (Operations/Finance/Communication/Administration) avec item actif visible.

## Activites avec/sans professeur + paie prof a 0 eleve

### Regles fonctionnelles
- Une activite definit maintenant explicitement si un professeur est requis (`course_types.requires_professor`).
- Si `requires_professor = false`, une seance peut etre creee/modifiee sans `professor_id`.
- La paie/facturation professeur avec 0 eleve est autorisee si la grille de paie contient une regle `min_students = 0` (comportement conserve).

### Impacts techniques
- Migration Alembic:
  - `course_types.requires_professor` (BOOLEAN, default true, not null)
  - `course_sessions.professor_id` passe nullable
- API admin:
  - `POST/PATCH /api/v1/admin/activities` accepte `requires_professor`
  - `POST/PATCH /api/v1/admin/sessions` accepte `professor_id = null` si activite sans professeur
- Listing sessions (catalogue/client/admin):
  - jointure professeur en `outer join` pour ne plus cacher les seances sans professeur.

### Validation
1. BO > Configuration > Activites: cocher/decocher `Professeur requis`.
2. BO > Planning: creer un creneau sur une activite sans professeur avec `Coach = Sans professeur`.
3. Verifier la visibilite du creneau dans les listes sessions.
4. Verifier la paie prof sur une activite avec regle `min_students = 0`:
   - generation releve/facture prof possible meme sans eleve.
