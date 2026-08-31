# Correction de la sélection de l'élève dans les devis

## Cause

Le sélecteur annuel ne cherchait que des clients mineurs. Le prospect enfant du devis pouvait donc exister et être rattaché à son parent sans apparaître. L'initiation n'était pas classée parmi les cours éligibles. Le filtre d'activité contenant « ado » excluait également les adultes des cours mixtes.

## Garanties

- Source de sélection : enfant précis du devis, ou destinataire adulte et ses enfants explicitement rattachés. Les prospects convertis sont dédupliqués avec leur client ; aucun rapprochement par nom/email.
- Les prospects non convertis conservent leurs preuves saisonnières et références familiales en métadonnées, sans insérer leur UUID dans les tables réservées aux clients. Aucune migration de données ni création de compte.
- Aperçu/confirmation, verrouillage familial, contrôle de version et audit restent requis. Les modifications de fiche ou de liens familiaux invalident un aperçu périmé.
- L'intégration et son annulation résolvent l'identité client d'une décision prospect par le lien de conversion explicite ; elles n'utilisent pas l'UUID prospect comme identifiant de contrat.
- Initiation, éveil musical, collectif enfant et cours mixtes ado/adultes sont reconnus séparément. Les adultes utilisent leur catégorie catalogue et n'obtiennent pas les remises mineurs. Pas de nouveaux droits tarifaires sur les offres non annuelles.
- Les remises manuelles restent bloquantes jusqu'au choix conserver/remplacer, puis confirmation. Les produits et les devis envoyés ne sont pas recalculés implicitement.
- Champs tactiles d'au moins 44 px et grille à une colonne sur petit écran.

## Vérification reproductible

Sur une base PostgreSQL isolée nommée `piano_annual_pricing_metadata`, avec le schéma de l'application, définir `ANNUAL_PRICING_TEST_DATABASE_URL`, puis lancer `pytest tests/test_annual_pricing_students_postgres.py tests/test_annual_pricing_postgres.py tests/test_annual_discounts.py`. Les fixtures utilisent des transactions annulées. Ne jamais utiliser une base de production.

Le test de régression Paul reproduit les 31 séances d'initiation, la remise fidélité de −62 €, le kit à 150 € et la partition à 25 €. Avec conservation explicite, le total reste 1 291 €, les identifiants et montants restent inchangés et aucun client n'est créé. D'autres cas couvrent les prospects adultes, l'éveil musical, les adolescents, les liens familiaux, la conversion et les aperçus périmés.

Interface : `node --experimental-strip-types --test scripts/test-annual-pricing-selection.mjs`, vérification TypeScript et compilation Next.js de production. Contrôle interactif complémentaire du vrai composant React avec une API simulée locale, dont une vue de 390 px ; ce contrôle UI n'enregistre rien en production.
