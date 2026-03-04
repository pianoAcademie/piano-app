# Plan Professeurs Multi-entites (PR1 -> PR6)

## PR1 - Schema DB et modeles
- Ajouter les colonnes prof facturation:
  - `professors.teacher_invoice_counter` (INT, default 1, not null)
  - `professors.teacher_is_vat_applicable` (BOOL, default false, not null)
  - `professors.teacher_vat_rate` (NUMERIC(5,2), nullable)
  - `professors.teacher_siret` (TEXT, nullable)
  - `professors.teacher_iban` (TEXT, nullable)
  - `professors.teacher_company_name` (TEXT, nullable)
  - `professors.teacher_company_address` (TEXT, nullable)
- Ajouter payeur legal entity:
  - `course_types.payor_legal_entity_id` FK `legal_entities(id)` (nullable -> backfill -> not null)
  - `course_sessions.snapshot_payor_legal_entity_id` FK `legal_entities(id)` (nullable -> backfill -> not null)
- Creer les tables:
  - `teacher_monthly_statements`
  - `teacher_invoices`
  - `teacher_invoice_lines`
  - `teacher_statement_messages`
  - `teacher_invoice_audit_events`
  - `document_templates`
- Impacts fichiers:
  - `backend/alembic/versions/*teacher_invoicing*.py`
  - `backend/app/models/catalog.py`
  - `backend/app/models/__init__.py`
  - `backend/app/models/teacher_invoicing.py` (nouveau)

## PR2 - BO collaborateurs + acces securise
- Etendre schemas/API collaborateurs (lecture/edition) avec champs facturation prof.
- Remplacer envoi de mot de passe temporaire par reset-link one-time.
- Ajouter endpoint admin:
  - `POST /api/v1/admin/collaborators/{id}/send-password`
- Utiliser `password_reset_tokens` existant (token hash, expiration, usage unique).
- Impacts fichiers:
  - `backend/app/schemas/admin.py`
  - `backend/app/api/routes/admin_collaborators.py`
  - `frontend/lib/types.ts`
  - `frontend/lib/actions.ts`
  - `frontend/app/admin/professors/[professorId]/page.tsx`

## PR3 - Template facture professeur administrable + preview PDF
- Ajouter service template HTML DB via `document_templates(key='teacher_invoice')`.
- Endpoints admin:
  - `GET /api/v1/admin/teacher-invoice-template`
  - `PUT /api/v1/admin/teacher-invoice-template`
  - `POST /api/v1/admin/teacher-invoice-template/preview`
- Generation PDF prof depuis template (fallback template par defaut si absent).
- Impacts fichiers:
  - `backend/app/api/routes/admin_collaborators.py` (ou route dediee)
  - `backend/app/services/teacher_invoice_documents.py` (nouveau)
  - `frontend/app/admin/teacher-invoicing/template/page.tsx` (nouveau)
  - `frontend/lib/actions.ts`
  - `frontend/lib/types.ts`

## PR4 - Teacher statements (portail prof)
- Endpoints:
  - `GET /api/v1/teacher/statements?year=&month=`
  - `GET /api/v1/teacher/statements/{year}/{month}`
  - `POST /api/v1/teacher/statements/{year}/{month}/dispute`
- Calcul par `(teacher, payor_legal_entity, year, month)` base sessions reelles.
- Blocage attendance incomplete + liste sessions manquantes.
- Impacts fichiers:
  - `backend/app/schemas/professor.py`
  - `backend/app/api/routes/teacher_invoicing.py`
  - `backend/app/services/teacher_invoicing.py` (nouveau)
  - `frontend/app/prof/statements/page.tsx` (nouveau)
  - `frontend/app/prof/statements/[year]/[month]/page.tsx` (nouveau)

## PR5 - Approbation + generation factures prof multi-entites
- `POST /api/v1/teacher/statements/{year}/{month}/approve`
  - 1 facture par payeur legal entity
  - compteur global professeur (`teacher_invoice_counter`) avec lock `FOR UPDATE`
  - due_date = invoice_date + 30 jours
  - TVA selon champs prof
- Endpoints factures prof:
  - `GET /api/v1/teacher/invoices?year=&month=`
  - `GET /api/v1/teacher/invoices/{invoice_id}`
  - `GET /api/v1/teacher/invoices/{invoice_id}/pdf`
- Impacts fichiers:
  - `backend/app/api/routes/teacher_invoicing.py`
  - `backend/app/services/teacher_invoice_documents.py` (nouveau)
  - `frontend/app/prof/invoices/[invoiceId]/page.tsx` (nouveau)
  - `frontend/app/prof/page.tsx` (lien menu Releves)

## PR6 - Actions facture + compta + audit + smokes
- Endpoints:
  - `POST /api/v1/teacher/invoices/{invoice_id}/cancel`
  - `POST /api/v1/teacher/invoices/{invoice_id}/uncancel`
  - `POST /api/v1/teacher/invoices/{invoice_id}/send-to-accounting`
- Destination email compta:
  - `legal_entities.accounting_email` si present
  - fallback `app_settings['comptability_email']`
- Ajouter audit events (generation, approve, cancel, uncancel, send-to-accounting, dispute, send-password).
- Ajouter smoke:
  - `backend/scripts/smoke_teacher_invoicing_v1.py`
- Validation a chaque jalon:
  - `docker compose exec -T backend alembic upgrade head`
  - `docker compose exec -T backend python scripts/smoke_v1.py`
  - `docker compose exec -T backend python scripts/smoke_billing_entities_v1.py`
  - `docker compose exec -T backend python scripts/smoke_teacher_invoicing_v1.py`
  - `docker compose exec -T frontend npm run build`

## PR7 - Activites avec/sans professeur
- Ajouter le parametre activite `requires_professor`.
- Autoriser la creation/modification de seances sans professeur quand l activite le permet.
- Conserver la facturation prof a 0 eleve quand une regle de grille `min_students = 0` existe.
- Impacts fichiers:
  - `backend/alembic/versions/20260307_0059_activity_requires_professor.py`
  - `backend/app/models/catalog.py`
  - `backend/app/schemas/admin.py`
  - `backend/app/schemas/catalog.py`
  - `backend/app/api/routes/admin.py`
  - `backend/app/api/routes/admin_config.py`
  - `backend/app/api/routes/catalogue.py`
  - `backend/app/api/routes/clients.py`
  - `backend/app/services/payouts.py`
  - `frontend/app/admin/config/page.tsx`
  - `frontend/app/admin/page.tsx`
  - `frontend/app/dashboard/page.tsx`
  - `frontend/lib/actions.ts`
  - `frontend/lib/types.ts`
