# Application mobile professeur — préparation et publication

## Résultat préparé

L'espace professeur dispose de trois modes d'installation qui utilisent tous le portail de production comme source de vérité :

1. **Installation immédiate depuis le navigateur** : le professeur ouvre l'onglet `Profil`, choisit `Installer l'application`, puis ajoute l'app à son écran d'accueil.
2. **iPhone/iPad** : app Capacitor dédiée, bundle `com.pianoacademie.professeur`, distribuable par TestFlight puis par l'App Store.
3. **Android** : app Capacitor dédiée, package `com.pianoacademie.professeur`, distribuable par le test interne Google Play puis par le Play Store.

L'application ouvre directement `https://app.piano-academie.com/prof`. Elle nécessite une connexion Internet. Aucune donnée professeur, élève ou de session n'est mise en cache hors ligne par le service worker.

## Identité de l'application

- Nom : `Piano Academie Professeur`
- Bundle ID / package : `com.pianoacademie.professeur`
- Catégorie : Éducation
- URL de support : `https://app.piano-academie.com/support`
- URL de confidentialité : `https://app.piano-academie.com/privacy`
- URL de connexion : `https://app.piano-academie.com/prof`
- Icône et écran de lancement : identité noire et dorée Piano Academie
- Socle natif : Capacitor 8.4.2, Android cible API 36, iOS minimum 15

## Validation automatique

Depuis `frontend` :

```bash
npm ci
npm run mobile:verify:prof
```

Cette commande vérifie les identifiants iOS/Android, l'URL de production, les projets natifs, les icônes et le service worker d'installation.

## iPhone / iPad — TestFlight et App Store

### Prérequis externes

- adhésion Apple Developer active pour Piano Academie ;
- identifiant `com.pianoacademie.professeur` créé dans Certificates, Identifiers & Profiles ;
- profil de distribution nommé `Piano Academie Professeur App Store` installé sur le Mac ;
- fiche d'app créée dans App Store Connect avec le SKU `PA-PROF-IOS` ;
- compte professeur de démonstration sans vraies données personnelles pour la review.

### Synchroniser et tester

```bash
cd frontend
npm run mobile:sync:prof
npm run mobile:prepare:prof
npm run mobile:open:prof
```

Dans Xcode, sélectionner une équipe de signature puis tester sur un iPhone réel : connexion, déconnexion, planning, saisie des présences, messages, lien Zoom, relevés et téléchargement PDF.

### Créer l'archive

```bash
cd frontend
npm run mobile:archive:prof:ios
```

L'archive est créée dans `frontend/build/PianoAcademieProfesseur.xcarchive`. La transmettre ensuite à App Store Connect depuis Xcode Organizer, puis commencer par un groupe TestFlight interne.

## Android — test interne et Play Store

### Prérequis externes

- compte Google Play Console de l'organisation ;
- Android Studio à jour, JDK 21 et SDK Android 36 installés ;
- fiche d'application créée avec le package immuable `com.pianoacademie.professeur` ;
- clé d'upload Android conservée hors du dépôt ;
- compte professeur de démonstration sans vraies données personnelles.

Créer une seule fois une clé d'upload (adapter le chemin vers un emplacement sauvegardé et privé) :

```bash
keytool -genkeypair -v \
  -keystore /chemin/prive/piano-academie-prof-upload.jks \
  -alias piano-academie-prof-upload \
  -keyalg RSA -keysize 2048 -validity 10000
```

Préparer les variables sans les écrire dans Git :

```bash
export PA_PROF_KEYSTORE_PATH=/chemin/prive/piano-academie-prof-upload.jks
export PA_PROF_KEYSTORE_PASSWORD='...'
export PA_PROF_KEY_ALIAS=piano-academie-prof-upload
export PA_PROF_KEY_PASSWORD='...'
export PA_PROF_VERSION_CODE=1
export PA_PROF_VERSION_NAME=1.0.0
```

Créer l'Android App Bundle signé :

```bash
cd frontend
npm run mobile:bundle:prof:android
```

Le fichier à déposer dans la Play Console est généré sous `frontend/android/app/build/outputs/bundle/release/`. Activer Play App Signing et commencer par le canal de test interne.

À chaque nouvelle version Android, incrémenter impérativement `PA_PROF_VERSION_CODE`.

## Installation immédiate sans Store

### iPhone / iPad

1. Ouvrir `https://app.piano-academie.com/prof` dans Safari.
2. Se connecter, puis ouvrir `Profil` et `Installer l'application`.
3. Toucher `Partager`, puis `Sur l'écran d'accueil`, puis `Ajouter`.

### Android

1. Ouvrir `https://app.piano-academie.com/prof` dans Chrome.
2. Se connecter, puis ouvrir `Profil` et `Installer l'application`.
3. Toucher `Installer l'application`. Si le bouton système n'est pas proposé, utiliser le menu Chrome puis `Ajouter à l'écran d'accueil`.

## Vérifications avant invitation des professeurs

- compte professeur actif et mot de passe testé ;
- redirection vers le portail professeur, jamais vers l'administration ou le portail client ;
- persistance de session après fermeture/réouverture ;
- planning et fuseau horaire corrects ;
- présence saisissable sur mobile ;
- liens Zoom ouverts ;
- PDF de relevé téléchargé ou affiché ;
- déconnexion fonctionnelle ;
- session expirée renvoyant vers la connexion professeur ;
- support et confidentialité accessibles publiquement ;
- aucune donnée réelle visible sur les captures Store ou le compte de review.

## Éléments restant à fournir au moment de publier

Le code et les projets sont prêts, mais ces éléments appartiennent aux comptes de l'école et ne doivent pas être stockés dans le dépôt :

- accès Apple Developer/App Store Connect et validation des accords en cours ;
- profil Apple de distribution professeur ;
- accès Google Play Console ;
- clé d'upload Google et mots de passe ;
- emails du premier groupe de testeurs ;
- identifiants du compte professeur de démonstration ;
- validation finale des déclarations de confidentialité et des textes juridiques.
