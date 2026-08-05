# Application mobile client — iOS et Android

Cette application embarque uniquement l'espace client Piano Academie. L'administration et le portail professeur restent hors de cette application.

## Identite conservee

- Nom: `Piano Academie Client`
- iOS bundle ID: `com.pianoacademie.client`
- Android application ID: `com.pianoacademie.client`
- URL de depart: `https://app.piano-academie.com/client`
- Version initiale: `1.0` (build `1`)

La premiere version iOS existante est conservee. Le projet Android utilise une variante `client`; la variante `professeur` existante reste disponible sans partager les sessions ni les identifiants Store.

## Verification commune

```bash
cd frontend
npm ci
npm run mobile:verify:client
```

## iOS

Preparer et compiler la version client:

```bash
cd frontend
npm run mobile:sync:client
npm run mobile:prepare:client
xcodebuild \
  -workspace ios/App/App.xcworkspace \
  -scheme App \
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro,OS=26.3' \
  build
```

Creer une archive App Store:

```bash
PA_CLIENT_VERSION_NAME=1.0 PA_CLIENT_VERSION_CODE=1 \
  npm run mobile:archive:client:ios
```

L'archive est creee dans `frontend/build/PianoAcademieClient.xcarchive`. La signature Release reste geree automatiquement par Xcode.

## Android

Compiler l'Android App Bundle du client:

```bash
cd frontend
npm run mobile:bundle:client:android
```

Variables de version et de signature:

```text
PA_CLIENT_VERSION_NAME=1.0
PA_CLIENT_VERSION_CODE=1
PA_CLIENT_KEYSTORE_PATH=/chemin/vers/upload-key.jks
PA_CLIENT_KEYSTORE_PASSWORD=...
PA_CLIENT_KEY_ALIAS=...
PA_CLIENT_KEY_PASSWORD=...
```

Le bundle est cree dans `frontend/android/app/build/outputs/bundle/clientRelease/`. Le workflow GitHub `Build client mobile apps` compile egalement un AAB de controle sans exiger les outils Android sur le Mac.

## Tests avant diffusion

- connexion et deconnexion d'un client;
- planning, changement de semaine, filtres et reservation;
- reconnaissance des abonnements et carnets existants;
- achat et retour Stripe;
- factures et documents PDF;
- messages et liens externes;
- session expiree et reconnexion;
- navigation iPhone et Android avec barre systeme et clavier ouverts.

## Elements externes encore necessaires pour publier

- acces App Store Connect au compte Piano Academie et fiche iOS liee a `com.pianoacademie.client`;
- acces Google Play Console et creation de l'app `com.pianoacademie.client`;
- cle d'upload Android, a sauvegarder durablement;
- captures Store realisees avec un compte de demonstration sans donnees reelles;
- validation des reponses App Privacy et Google Play Data Safety;
- acceptation des contrats et informations bancaires/fiscales des Stores.

La creation des archives et leur televersement ne publient rien automatiquement. TestFlight et les pistes de test Google Play doivent etre valides avant toute mise en production publique.
