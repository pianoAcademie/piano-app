# Suivi pédagogique par morceau

Dans les présences du portail professeur, chaque élève dispose d'une carte mobile :

- **Continuer ce morceau** enregistre le travail du cours sans terminer le morceau.
- **Terminé → suivant** termine explicitement le morceau actuel et propose un suivant, librement modifiable, sans imposer l'ordre du catalogue.
- **Corriger** change la partition ou le morceau actuel sans déclarer les précédents terminés.
- **Reprendre l'historique** permet de cocher les morceaux déjà terminés dans n'importe quel ordre. Le raccourci « Tous avant le morceau actuel » accepte ensuite des exceptions. Les autres morceaux restent à vérifier ou peuvent être marqués à reprendre.
- **Voir le suivi** affiche les états par partition et les dernières actions datées avec leur auteur.
- Une confirmation visible suit chaque sauvegarde. La dernière action peut être annulée par son auteur tant qu'aucune autre modification n'a été enregistrée.

La partition n'est terminée qu'après confirmation et lorsque tous ses morceaux sont terminés. Le choix de la suivante reste explicite. Un catalogue sans morceaux ne permet pas de valider automatiquement une partition entière.

## Reprise et intégrité

Le premier affichage reprend la partition en cours et le morceau de l'ancien suivi, ainsi que la note interne. Il ne déduit aucune progression passée. La saisie d'historique est identifiée comme reprise, sans inventer de date de fin ; une date de fin déjà connue est conservée si le statut n'est pas changé.

Le suivi pédagogique est séparé de la distribution physique (`student_sheet_music`). Une correction ne consomme aucun stock, ne modifie pas une livraison et ne facture rien. La remise physique reste à confirmer dans **Mes partitions**. Les anciennes vues administratives du répertoire continuent d'afficher les données de distribution ; elles ne doivent pas être utilisées comme lecture du nouveau suivi par morceau.

Les endpoints professeur contrôlent le rattachement de l'élève au cours du professeur (titulaire, remplaçant ou co-intervenant). Les écritures verrouillent l'élève et vérifient une révision pour refuser un écran périmé. Chaque action conserve ses états avant/après, son auteur et le cours associé.

## Livraison technique

Migration additive `20260905_0242` : `student_learning_progress` et `student_learning_events`. Appliquer la migration avant de démarrer le backend et le frontend correspondants. Ne pas supprimer ces tables lors d'un retour applicatif après utilisation.

Avant tout déploiement : relever de nouveau les sources et images réellement en production, comparer la branche et intégrer les changements concurrents.

## Production — 5 septembre 2026

Déployé à la demande de l'utilisateur, code `cdbdd879`. Socle `fb52bae8` vérifié avant préparation puis immédiatement avant bascule : 800 fichiers identiques. Après bascule : 807 fichiers identiques au code attendu.

Migration `20260905_0242` appliquée. Backend sain, connexion publique HTTP 200, portail professeur protégé par redirection d'authentification. Contrôle en transaction strictement en lecture seule : 5 cours, 11 suivis élèves cohérents entre liste des présences et endpoint pédagogique. Aucun changement de suivi élève, paiement ou email de test en production.

Les 41 tests locaux de l'implémentation sont complétés par 28 tests unitaires/répertoire dans une instance jetable de l'image serveur. Build frontend de production réussi. Les services de notifications n'ont pas été redémarrés.

- Image backend : `sha256:5f447ccd7b0ad1b6ef1fb47d693c51393a457da381e19aafbd83160c6aa986ae`.
- Image frontend : `sha256:53b8b36ca4dd2943b96fb22d0372891f12f89cd8be922b5156e8ce2d3ad44129`.
- Backend construit sur l'image de production précédente pour conserver exactement ses dépendances ; recette `/home/ubuntu/teacher-learning-cdbdd879/backend-deploy.Dockerfile`.
- Sauvegardes sources et base : `/home/ubuntu/teacher-learning-cdbdd879/pre-rollout-sources.tgz` et `pre-rollout-db.dump` (accès restreint).
- Images de retour arrière : `piano-learning-rollback-backend:fb52bae8`, `piano-learning-rollback-frontend:fb52bae8`. Restaurer les sources correspondantes et ces images ensemble après contrôle d'éventuels changements concurrents ; conserver les tables additives et les nouvelles données pédagogiques.

## Vérifications locales

- Migration complète sur une base PostgreSQL 16 isolée : réussie.
- 41 tests réussis : transitions, reprise sans dates inventées, notes existantes, correction, annulation, persistance/rechargement, permissions, révisions concurrentes et non-régression distribution/répertoire.
- TypeScript et build Next de production : réussis (avertissements préexistants dans globals.css).
- Contrôle navigateur sur une carte de démonstration à 320, 375 et 768 px : pas de débordement horizontal ; raccourci historique, exceptions et sélection du morceau corrigé vérifiés. Ce contrôle visuel ne remplace pas un essai connecté complet après déploiement.

Commande tests : `python -m pytest -q tests/test_learning_progress.py tests/test_learning_progress_db.py tests/test_repertoire_progression.py tests/test_partition_distribution.py` avec `PARTITION_TEST_DATABASE_URL` pointant uniquement sur une base de test.
