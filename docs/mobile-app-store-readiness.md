# Mobile apps readiness

Objectif: preparer deux apps mobiles publiques ou TestFlight, une pour les clients et une pour les professeurs, en reutilisant les portails web existants. L'administration reste reservee au navigateur.

## Decision recommandee

Demarrer par TestFlight jusqu'a la stabilisation fonctionnelle de septembre. Cela permet de tester les parcours reels sans exposer une app instable dans l'App Store public.

## Entrees applicatives

- App client: `/client`
- App professeur: `/prof`
- Admin: `/admin`, non embarque dans l'app mobile

## Premiere couche livree

- Metadata iOS globale dans le layout Next.js.
- Manifeste dedie client: `/client/manifest.webmanifest`.
- Manifeste dedie professeur: `/prof/manifest.webmanifest`.
- Icones applicatives partagees dans `/app-icons/`.
- Raccourcis planning, finance/messages cote client.
- Raccourcis planning, feuilles/messages cote professeur.

## Suite technique conseillee

1. Auditer les parcours mobiles critiques: connexion, planning, paiement, messages, feuilles professeurs, presence.
2. Utiliser Capacitor comme wrapper iOS leger, avec deux configurations: `PA Client` et `PA Prof`.
3. Forcer chaque configuration a ouvrir son entree dediee et a bloquer l'acces direct admin.
4. Tester les cookies de session dans WKWebView, les liens PDF, paiements Stripe/Oney et retours depuis navigateur externe.
5. Publier une premiere version TestFlight interne, puis externe.

## Base Capacitor

La configuration Capacitor est disponible cote frontend:

- `frontend/capacitor.config.ts`

Elle est pilotee par `MOBILE_APP_TARGET=client` ou `MOBILE_APP_TARGET=prof`.

Commandes prevues:

```bash
cd frontend
npx cap add ios
npm run mobile:sync:client
npm run mobile:prepare:client
npm run mobile:open:client
npm run mobile:sync:prof
npm run mobile:prepare:prof
npm run mobile:open:prof
```

Les deux apps chargent volontairement l'URL de production dediee:

- Client: `https://app.piano-academie.com/client`
- Professeur: `https://app.piano-academie.com/prof`

Cette approche evite de transformer l'app Next.js SSR en export statique. Elle est adaptee pour TestFlight et une premiere validation terrain.

Etat actuel: la configuration Capacitor, les dependances et le dossier natif `frontend/ios` sont prets avec une premiere configuration client. L'orientation iOS est limitee au portrait et l'icone d'app reprend l'icone Piano Academie.

Un manifeste de confidentialite natif est present dans `frontend/ios/App/App/PrivacyInfo.xcprivacy`. Il declare uniquement la couche native iOS: pas de tracking natif, pas de domaine de tracking natif, pas de collecte native. Les donnees collectees par le portail web doivent toujours etre renseignees dans les labels App Store Connect et rester coherentes avec la politique de confidentialite publique.

## Separation des deux apps iOS

Capacitor genere un projet iOS de base. Pour TestFlight, il faut ensuite creer deux apps distinctes dans Xcode:

- Target `Piano Academie Client`
  - Bundle ID: `com.pianoacademie.client`
  - URL de depart: `https://app.piano-academie.com/client`
- Target `Piano Academie Professeur`
  - Bundle ID: `com.pianoacademie.professeur`
  - URL de depart: `https://app.piano-academie.com/prof`

Approche conseillee:

1. Lancer `npm run mobile:sync:client` puis `npm run mobile:prepare:client` pour archiver l'app client.
2. Ouvrir `frontend/ios/App/App.xcworkspace` et creer l'archive Xcode.
3. Lancer `npm run mobile:sync:prof` puis `npm run mobile:prepare:prof` pour archiver l'app professeur.
4. Ouvrir le meme workspace et creer l'archive Xcode professeur.
5. Garder un seul code web: les deux archives affichent les routes existantes du portail.

Fichiers de configuration natifs prets pour la duplication:

- `frontend/ios/App/App/capacitor.client.config.json`
- `frontend/ios/App/App/capacitor.prof.config.json`

Le script `frontend/scripts/prepare-ios-target.mjs` met a jour le nom affiche, le bundle ID Xcode et le fichier `capacitor.config.json` actif avant chaque archive.

## Deploiement

Pendant la phase de validation devis/production active, le workflow VPS doit rester declenche manuellement uniquement. Cela evite qu'un simple push sur `main` relance une prod pendant que des clients valident des devis.

## Points App Store a traiter avant soumission publique

- Compte Apple Developer et identifiants bundle separes.
- Politique de confidentialite accessible publiquement: premiere URL technique disponible sur `/privacy`.
- Mentions de support et contact: premiere URL technique disponible sur `/support`.
- Captures iPhone requises pour chaque app.
- Clarifier les paiements: si les paiements concernent des cours physiques, ils peuvent rester web/Stripe hors achat in-app.
- Eviter toute promesse marketing non stabilisee dans la fiche App Store.

## Plan de livraison conseille

### Phase 1 - maintenant

- Garder la production web comme source de verite.
- Tester les apps iOS via TestFlight interne avec comptes reels de test.
- Valider les parcours client: connexion, planning, paiement, documents, messages.
- Valider les parcours professeur: planning, presence, feuilles, messages.
- Ne pas publier sur l'App Store public tant que les releases devis/planning restent frequentes.

### Phase 2 - stabilisation septembre

- Ouvrir TestFlight externe a quelques familles et professeurs.
- Finaliser les textes App Store, captures et politique de confidentialite complete.
- Creer deux fiches App Store separees: client et professeur.
- Soumettre l'app client en premier, puis l'app professeur apres validation terrain.

### Phase 3 - publication publique

- Passer chaque app en review App Store.
- Garder l'administration sur navigateur uniquement.
- Maintenir les updates mobiles comme des shells legers pointant vers la production web.
