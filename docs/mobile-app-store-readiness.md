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
2. Ajouter un wrapper iOS leger, probablement Capacitor, avec deux schemes ou deux targets: `PA Client` et `PA Prof`.
3. Forcer chaque target a ouvrir son entree dediee et a bloquer l'acces direct admin.
4. Tester les cookies de session dans WKWebView, les liens PDF, paiements Stripe/Oney et retours depuis navigateur externe.
5. Publier une premiere version TestFlight interne, puis externe.

## Points App Store a traiter avant soumission publique

- Compte Apple Developer et identifiants bundle separes.
- Politique de confidentialite accessible publiquement.
- Mentions de support et contact.
- Captures iPhone requises pour chaque app.
- Clarifier les paiements: si les paiements concernent des cours physiques, ils peuvent rester web/Stripe hors achat in-app.
- Eviter toute promesse marketing non stabilisee dans la fiche App Store.
