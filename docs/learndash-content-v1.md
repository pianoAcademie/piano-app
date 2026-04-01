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
- `replace_course_type_content_mappings(...)`

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

The admin back-office also exposes these settings directly in `Configuration > Activites`, so editing
`app_settings` manually is optional.

## WordPress plugin

A minimal WordPress plugin is bundled in this repository:

- `wordpress/plugins/piano-academie-learndash-bridge`

It exposes:

- `/wp-json/piano/v1/courses`

and can protect the endpoint with a bearer token configured from the WordPress admin.

## Current limits

- read-only content sync
- BO mapping is limited to the admin configuration screen for activities
- client access is derived from active subscriptions / enrollments only
- no progress tracking
- no deletion of missing courses globally, because a sync endpoint may expose only a subset
- missing sections and lessons **inside a synced course** are removed during sync, because WordPress is the source of truth for that course outline

## Admin usage

The back-office now exposes two building blocks for V1:

- a "Synchroniser LearnDash" action in `Configuration > Activites`
- a per-activity content assignment area in the create/edit activity modal

Recommended sequence:

1. install the WordPress plugin `piano-academie-learndash-bridge`
2. configure the WordPress / LearnDash connection in `Configuration > Activites`
3. run the catalog sync from the BO
4. open an activity such as `Cours de solfege en ligne - Niveau 1`
5. attach one or more synced content courses

The intended business rule remains:

- WordPress / LearnDash stores the pedagogical catalog
- Piano Academie decides which students can access which content
- access is derived from the student's active enrollment on the mapped activity

## Client portal usage

The client portal now exposes a `Mes cours` tab.

This tab:

- lists the synced courses available for the family
- lets the user filter by family member
- shows the course outline with sections and lessons
- renders lesson HTML synced from WordPress / LearnDash

Current access rule for the portal:

- a content course is visible when one of the user's active subscriptions exposes a `course_type`
- and this `course_type` is mapped to one or more external content courses
