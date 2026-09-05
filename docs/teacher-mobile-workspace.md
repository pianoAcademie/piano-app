# Portail professeur : parcours mobile complet

Base initiale : `fe88a6dc`. Avant déploiement, intégration du déploiement intermédiaire `688f5695` (correction des créneaux de devis), dont les 807 fichiers opérationnels contrôlés correspondent exactement à la production. Aucun changement du backend, des paiements, des réservations ou de la distribution des partitions dans le correctif mobile.

## Changements

- Un élève à la fois, sélection directe et précédent/suivant. Le sélecteur reste accessible pendant le défilement. Retour en haut à chaque changement.
- Les éditeurs des autres élèves restent montés mais masqués, afin de conserver les brouillons. Le dernier élève sélectionné est mémorisé pour le cours dans la session du navigateur.
- Une seule zone de défilement dans la fenêtre. Informations du groupe repliées. En-tête et pied hors de la zone défilante, hauteur dynamique et marges de sécurité iOS.
- Fermeture par croix, retour au planning ou Échap. Confirmation avant abandon d'une saisie et blocage pendant une sauvegarde. Confinement du focus clavier et verrouillage du défilement de la page arrière.
- Progression : deux actions quotidiennes, continuer ou terminer. Choix initial unique si le morceau manque ; correction et reprise d'historique placées dans un volet explicitement nommé.
- Boutons secondaires neutres et alignés, calendrier à une colonne sur mobile, contrôles date/vue compacts, suppression du bandeau d'identité dupliqué sur mobile.

Les règles de sauvegarde et d'audit pédagogiques déjà testées restent inchangées.

## Vérification reproductible

Résultat local : parcours réussi sous Chromium et WebKit aux trois largeurs ; contrôle explicite d'une cible de sélection d'au moins 44 px sous WebKit. Compilation de production réussie, avec les deux avertissements CSS préexistants dans globals.css.

Le test `frontend/tests/teacher-mobile-browser.mjs` monte temporairement une page de démonstration complète, démarre Next sur le port 3019 puis retire cette page à la fin. Il utilise les composants réels et le CSS global, et non une carte isolée. Ne pas lancer pendant un build ni si un autre serveur occupe le port 3019.

Avec Playwright disponible : `node tests/teacher-mobile-browser.mjs` depuis frontend. Utiliser `QA_WEBKIT=1` pour WebKit ; `PLAYWRIGHT_MODULE` et `CHROME_EXECUTABLE` permettent de pointer vers les runtimes locaux. Les captures sont placées dans `QA_ARTIFACT_DIR` ou le répertoire temporaire du système.

Scénarios : 320, 393 et 768 px ; navigation, brouillon conservé, un seul élève visible, absence de débordement, note du groupe repliée, annulation de fermeture, échec de sauvegarde sans perte du formulaire, fermeture avec hauteur réduite à 430 px et retour au planning.

Sur localhost HTTP, le harnais retire uniquement `upgrade-insecure-requests` de la réponse de démonstration, car WebKit essaie autrement de charger les ressources locales en HTTPS. Aucune règle de sécurité de l'application n'est modifiée.

Contrôles approfondis : action serveur Next réelle reliée à une API HTTP locale de test, sauvegarde réussie et confirmation visible, morceau terminé et suivant choisi hors ordre, blocage du changement d'élève pendant la sauvegarde, une requête par action, conflit HTTP 409 avec conservation du formulaire. Les 38 tests ciblés sur créneaux, réservations, remises et dates locales passent aussi sur la base fusionnée.

Limites : données de démonstration et API simulée ; ces tests ne créent aucune écriture sur un élève réel. La hauteur réduite simule l'espace réduit mais pas le clavier natif d'un iPhone. Un contrôle connecté sur appareil réel reste recommandé.

## Déploiement

Déployé le 5 septembre 2026 à 18:12 Europe/Paris, code `ceecaec1`. Dernier contrôle avant bascule : 811 fichiers identiques à `688f5695`, images frontend et backend inchangées depuis ce déploiement intermédiaire.

- Image frontend active : `sha256:9ce86beae0be2a3375fbe6c3d1280d6a746c948c0ee987aa1e9c57f4ea721710`.
- Backend non redémarré : `sha256:bc98310d2c228cb66d6a333f30e891c37bdbce72266bce73ea24bedfd82193ae`.
- Après bascule : 813 fichiers opérationnels identiques au code livré ; `/login` HTTP 200 ; `/prof` HTTP 307 sans authentification, attendu ; démarrage frontend sans erreur ; route de démonstration absente de l'image.
- Vérification de production en lecture seule avant bascule : 5 cours, 11 suivis élèves, migration 0242 présente. Aucune donnée métier modifiée pour les tests.
- Retour arrière conservé : image `piano-mobile-rollback:ceecaec1`, fichiers remplacés dans `/home/ubuntu/piano-mobile-rollback-ceecaec1/sources.tar.gz`. Restaurer ensemble les trois fichiers remplacés et l'image ; les deux nouveaux composants ne sont pas référencés par l'ancienne page.

Les parcours Chromium et WebKit passent sur 320, 393 et 768 px après intégration de la correction des devis. Compilation dans l'image Docker réussie (deux avertissements CSS préexistants). Le contrôle d'un clavier iPhone physique reste à effectuer.
