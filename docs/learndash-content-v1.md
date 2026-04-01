# LearnDash Content V1

## Goal

Use WordPress / LearnDash as the source of truth for pedagogical content while keeping access rights in Piano Academie.

## Data model

This V1 introduces four tables:

- `external_content_courses`
- `external_content_sections`
- `external_content_lessons`
- `course_type_content_mappings`

The first three mirror the content catalog coming from WordPress / LearnDash.
The mapping table links an internal `course_type` to one or more external content courses.

## Access model

The intended rule is:

- WordPress stores content
- Piano Academie stores who can access it
- a student gets access to content through an active enrollment on the mapped internal activity

This V1 does **not** add user progress, quiz state, certificates, or WordPress user synchronization.

## Sync service

The backend service is `app.services.external_content`.

Main entry points:

- `sync_wordpress_learndash_catalog(db, payload=...)`
- `sync_wordpress_learndash_catalog(db, endpoint_url=...)`
- `resolve_wordpress_learndash_sync_endpoint(db)`
- `upsert_course_type_content_mapping(...)`

Supported payload shapes:

- `{ "courses": [...] }`
- `[ ... ]`
- a single course object

Expected course structure:

- course
  - `id` or `external_id`
  - `title`
  - optional `slug`, `summary`, `level_code`, `status`, `cover_image_url`
  - optional `sections`
  - optional `lessons` or `standalone_lessons`

Expected section structure:

- section
  - `id` or `external_id`
  - `title`
  - optional `position`
  - optional `lessons`

Expected lesson structure:

- lesson
  - `id` or `external_id`
  - `title`
  - optional `slug`, `summary`, `content_html`, `video_url`, `resource_url`, `status`

## App settings

The sync service can be configured through `app_settings` with:

- `external_content.wordpress_learndash.base_url`
- `external_content.wordpress_learndash.courses_endpoint`
- `external_content.wordpress_learndash.bearer_token`
- `external_content.wordpress_learndash.timeout_seconds`

If `courses_endpoint` is not set, the service uses:

- `{base_url}/wp-json/piano/v1/courses`

## Current limits

- read-only content sync
- no BO UI yet for mappings
- no public/client API yet for "Mes cours"
- no progress tracking
- no deletion of missing courses globally, because a sync endpoint may expose only a subset
- missing sections and lessons **inside a synced course** are removed during sync, because WordPress is the source of truth for that course outline
