# Notifications mobiles — application client

Les notifications sont adressées uniquement aux clients ayant installé l’application et autorisé les notifications. Pour un élève enfant, le destinataire est le responsable de facturation. L’administration peut envoyer une notification depuis la fiche client ou depuis un créneau du planning.

## Configuration serveur

Activer le service avec `PUSH_NOTIFICATIONS_ENABLED=true`, puis configurer au moins un fournisseur.

### iOS / APNs

- `APNS_TEAM_ID` : identifiant de l’équipe Apple.
- `APNS_KEY_ID` : identifiant de la clé APNs.
- `APNS_PRIVATE_KEY` : contenu de la clé `.p8` (retours ligne réels, `\\n` ou préfixe `base64:` acceptés).
- `APNS_BUNDLE_ID=com.pianoacademie.client`.
- `APNS_USE_SANDBOX=false` en production/TestFlight.

Dans Apple Developer, l’identifiant `com.pianoacademie.client` doit avoir la capacité **Push Notifications**. Après `npm install`, exécuter `npx cap sync ios`, ouvrir le workspace Xcode, puis publier un nouveau build.

## Android / Firebase Cloud Messaging

- Ajouter le vrai fichier Firebase `google-services.json` dans `frontend/android/app/`. Ce fichier est ignoré par Git et ne doit jamais être versionné.
- `FIREBASE_PROJECT_ID` : identifiant du projet Firebase.
- `FIREBASE_CLIENT_EMAIL` et `FIREBASE_PRIVATE_KEY` : compte de service autorisé à envoyer via FCM HTTP v1.

Après `npm install`, exécuter `npx cap sync android`, puis publier un nouveau bundle Android.

## Contrôle fonctionnel

1. Installer le nouveau build sur un téléphone et se connecter au portail client.
2. Accepter la demande de notifications.
3. Depuis la fiche client admin, onglet Messages, envoyer une notification de test.
4. Vérifier l’état dans l’historique : envoyée, reçue ou ouverte.
5. Depuis un créneau, utiliser **Envoyer une notification** et sélectionner les participants.
