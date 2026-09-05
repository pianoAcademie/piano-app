# Portail professeur : parcours mobile complet

Base : `fe88a6dc`, dernière production au début du travail. Aucun changement du backend, des paiements, des réservations ou de la distribution des partitions.

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

Limites : données de démonstration, sauvegarde testée en échec de session ; ce test ne valide pas une nouvelle écriture réelle sur un élève. La hauteur réduite simule l'espace réduit mais pas le clavier natif d'un iPhone. Un contrôle connecté sur appareil réel reste recommandé avant diffusion générale.

## Déploiement

Non déployé pendant l'implémentation. Recontrôler les fichiers et images réellement en production immédiatement avant la bascule et intégrer tout changement concurrent. Le correctif est limité au frontend.
