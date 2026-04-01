# Piano Academie LearnDash Bridge

Petit plugin WordPress qui expose le catalogue LearnDash pour Piano Academie.

## Ce qu'il expose

- endpoint REST : `/wp-json/piano/v1/courses`
- provider : `WORDPRESS_LEARNDASH`
- cours
- sections
- lecons

Le format est compatible avec la synchro V1 de l'application Piano Academie.

## Installation

1. Copier le dossier `piano-academie-learndash-bridge` dans `wp-content/plugins/`
2. Activer le plugin dans WordPress
3. Aller dans `Settings > Piano Academie LearnDash`
4. Renseigner un token bearer si vous voulez proteger l'endpoint
5. Dans Piano Academie BO, section `Configuration > Activites`
6. Renseigner :
   - `URL du site WordPress`
   - ou `Endpoint cours`
   - et le meme token bearer si vous en avez configure un
7. Cliquer `Synchroniser LearnDash`

## Notes

- Si aucun token n'est configure dans WordPress, l'endpoint est public en lecture seule.
- Les `sfwd-courses` sont exportes comme `courses`.
- Les `sfwd-lessons` sont exportees comme `sections`.
- Les `sfwd-topic` sont exportes comme `lessons` quand ils existent.
- S'il n'y a pas de topic sous une lecon LearnDash, la lecon elle-meme est exposee comme unique lecon de la section.

## Champs utiles

Vous pouvez ajouter un code de niveau via un custom field sur le cours :

- `_piano_level_code`
- `piano_level_code`
- `course_level`
- `niveau`

Le plugin l'expose comme `level_code` pour aider au mapping dans Piano Academie.
