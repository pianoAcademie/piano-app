# Mobile apps readiness

Objectif: preparer les apps mobiles en reutilisant les portails web existants. La priorite actuelle est l'espace client iOS et Android. L'administration reste reservee au navigateur.

La premiere version iOS client est conservee sous `com.pianoacademie.client`. La version Android client utilise maintenant le meme identifiant applicatif et la meme route `/client`. Voir `docs/client-mobile-app-release.md` et `docs/client-mobile-app-store-listing.md`.

La chaîne professeur iOS, Android et installation web est maintenant documentée séparément dans `docs/professor-mobile-app-release.md`.

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
2. Utiliser Capacitor comme wrapper natif leger. iOS conserve deux configurations (`PA Client` et `PA Prof`) et Android dispose des variantes `client` et `professeur`.
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
npm run mobile:sync:prof:android
npm run mobile:open:prof:android
npm run mobile:verify:prof
npm run mobile:sync:client:android
npm run mobile:bundle:client:android
npm run mobile:verify:client
```

Les deux apps chargent volontairement l'URL de production dediee:

- Client: `https://app.piano-academie.com/client`
- Professeur: `https://app.piano-academie.com/prof`

Cette approche evite de transformer l'app Next.js SSR en export statique. Elle est adaptee pour TestFlight et une premiere validation terrain.

Etat actuel: la configuration Capacitor et les dossiers natifs `frontend/ios` et `frontend/android` sont prets. iOS peut etre bascule entre les cibles client et professeur; Android compile des variantes client et professeur distinctes. L'orientation iOS est limitee au portrait et les deux plateformes utilisent l'identite Piano Academie.

Un manifeste de confidentialite natif est present dans `frontend/ios/App/App/PrivacyInfo.xcprivacy`. Il declare uniquement la couche native iOS: pas de tracking natif, pas de domaine de tracking natif, pas de collecte native. Les donnees collectees par le portail web doivent toujours etre renseignees dans les labels App Store Connect et rester coherentes avec la politique de confidentialite publique.

Le workspace CocoaPods est initialise:

- `frontend/ios/App/App.xcworkspace`
- `frontend/ios/App/Podfile.lock`

Pour regenerer les Pods localement:

```bash
cd frontend
npm ci
cd ios/App
pod install
```

Sur cette machine, CocoaPods est disponible via l'installation Ruby utilisateur (`~/.gem/ruby/2.6.0/bin`). Apres installation du composant iOS dans Xcode, les deux configurations compilent en simulateur iPhone:

```bash
node frontend/scripts/prepare-ios-target.mjs client
xcodebuild -workspace frontend/ios/App/App.xcworkspace -scheme App -destination 'platform=iOS Simulator,name=iPhone 17 Pro,OS=26.3.1' build

node frontend/scripts/prepare-ios-target.mjs prof
xcodebuild -workspace frontend/ios/App/App.xcworkspace -scheme App -destination 'platform=iOS Simulator,name=iPhone 17 Pro,OS=26.3.1' build
```

Apres un build professeur, relancer `node frontend/scripts/prepare-ios-target.mjs client` pour remettre le projet dans l'etat client par defaut.

Validation locale du 23/05/2026:

- `docker compose run --rm frontend npm run build`: OK.
- Build iOS simulateur client: OK sur iPhone 17 Pro iOS 26.3.1.
- Build iOS simulateur professeur: OK sur iPhone 17 Pro iOS 26.3.1.
- `/prof` redirige maintenant vers `/login?portal=prof&return_to=%2Fprof` quand la session est absente.
- La page de connexion professeur affiche "Espace professeur" et masque la creation de compte client.

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
- Politique de confidentialite bilingue accessible publiquement sur `/privacy` et `/privacy?lang=en`.
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
- Finaliser les textes App Store et les captures, puis verifier la coherence des labels avec la politique de confidentialite publiee.
- Creer deux fiches App Store separees: client et professeur.
- Soumettre l'app client en premier, puis l'app professeur apres validation terrain.

### Phase 3 - publication publique

- Passer chaque app en review App Store.
- Garder l'administration sur navigateur uniquement.
- Maintenir les updates mobiles comme des shells legers pointant vers la production web.
