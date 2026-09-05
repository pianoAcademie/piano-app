# Restauration des essais enfants — 5 septembre 2026

## Cause vérifiée

L'évolution du 4 septembre était présente dans les modifications locales non commitées : publication explicite sur chaque séance, case du planning administrateur et compatibilité du calendrier intégré avec les essais sur cours collectifs ordinaires. La base avait déjà sa colonne `public_child_trial_listing_enabled` et conservait 475 séances publiées.

Le workflow `deploy-vps.yml` synchronise intégralement le dépôt par rsync avec `--delete`. Les déploiements de versions Git qui ne contenaient pas cette évolution ont écrasé les sources modifiées directement sur le serveur. Les runs 33859496048 (4c47417e, 11 h 40 Paris) et 33883790552 (4941e00c, 16 h 27) ont synchronisé les sources mais échoué au déploiement. Le run 33884650258 a réussi le 4 septembre de 16 h 36 min 07 s à 16 h 36 min 49 s : son commit dc4299f0 rétablit uniquement la migration 20260904_0240, sans les routes, modèles et interfaces de l'évolution. Ce redéploiement réussi confirme le retour à l'ancien comportement. Les déploiements ultérieurs ont conservé cette absence.

## Socle et restauration

Socle : 783b8056, confirmé comme HEAD de main et comparé aux fichiers réellement déployés (dont admin.py et le calendrier intégré), incluant les correctifs de réorganisation 6744e88e et distribution des partitions e3e195cd. Réintégration sélective des changements de publication, sans reprendre les autres modifications locales en cours.

Le mode public enfants respecte le choix de publication enregistré, les droits enfants/essai, les places restantes et les règles de l'évolution retrouvée (cours collectifs présentiels des professeurs configurés dans cette évolution). L'ancien lien WordPress est reconnu. La commande administrateur est conservée à la création, modification, extension et duplication de séance. Le parcours de connexion des essais publics sélectionne le public enfant, y compris pour les séances mixtes. La tarification des calendriers adultes reste inchangée.

## Vérification

39 tests ciblés réussis (publication, essais, prix, éligibilité et réorganisation). Vérification en lecture seule des publications de la semaine du 7 septembre : 10 séances disponibles, chacune avec une offre enfant à 20 EUR ; une autre séance publiée est complète. Aucun changement de publication ou de réservation effectué.

Le contrôle exhaustif de 548 fichiers avant bascule a détecté le déploiement concurrent 860a04db (ajustement du retrait des partitions). Ce commit a été intégré au socle avant reconstruction finale. Les calendriers publics ordinaires ont des empreintes JSON identiques avant/après : 85 séances sans filtre de public, 79 enfants et 52 adultes. Le calendrier intégré a été vérifié via l'ancien lien WordPress : 10 séances affichées, offre à 20 EUR et connexion orientée enfant.

Avant la bascule, vérifier de nouveau les sources et images actuelles. Sauvegarde actualisée : /home/ubuntu/child-trials-restore-20260905/pre-rollout-860a04db.tgz. Images candidates construites séparément des services en activité. Les scripts d'audit fournis n'effectuent que des lectures et imposent une transaction READ ONLY.

## Résultat du déploiement

Version applicative 65ba61cb déployée et enregistrée sur main. La compilation Next.js finale a réussi. En production, l'URL exacte intégrée dans WordPress affiche 10 séances disponibles sur la semaine du 7 septembre, les horaires locaux attendus, le tarif d'essai 20 EUR et le lien de connexion enfant. API saine. Aucune réservation ni aucun choix de publication modifié. Images de retour arrière : piano-child-trials-rollback-backend:860a04db et piano-child-trials-rollback-frontend:860a04db. Les workers, PostgreSQL et Redis sont restés en activité.
