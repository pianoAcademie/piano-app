# Lien de paiement partiel sur une facture existante

## Utilisation

Dans **Clients → fiche client → Factures**, choisir **Envoyer un lien de paiement partiel** sur une facture émise. Saisir le montant, contrôler les destinataires de facturation et le solde affiché, puis envoyer.

Exemple : facture de **1 096 €**, demande CB de **396 €**. L’envoi ne crée aucune transaction et le solde reste à 1 096 €. Après confirmation bancaire vérifiée, une transaction de 396 € est rapprochée de cette même facture ; **700 € restent dus**. Les espèces attendues ne sont jamais enregistrées par anticipation. À leur réception, saisir un paiement **Espèces de 700 €** et le rapprocher de la facture : celle-ci est alors soldée. Ni le numéro, ni les prestations, ni le montant initial de la facture ne changent.

Le client reçoit un courriel charté contenant le montant demandé, le solde prévu et le lien. Après confirmation bancaire, un reçu distinct indique le montant réellement reçu et le solde restant, sans annoncer à tort que toute la facture est payée.

## Garde-fous

- Facture émise non soldée, en EUR ; montant d’au moins 1 €, deux décimales au maximum, strictement inférieur au solde au moment de la demande.
- Lien nominativement rattaché à la facture et à une demande, signé, valable 30 jours. Le montant est fixé côté serveur, jamais repris du navigateur.
- Une seule demande active par facture. Son existence bloque le lancement d’un paiement concurrent du solde intégral par carte ou virement. Les anciens paiements du solde déjà ouverts doivent être vérifiés avant de créer une demande partielle.
- Demande annulable tant qu’aucun paiement bancaire n’est ouvert. Si la banque est encore en attente ou si la création a eu un résultat incertain, le système bloque une nouvelle tentative et demande un contrôle.
- Double clic et callbacks répétés : même demande / même tentative bancaire ; pas de deuxième transaction comptable.
- Vérification auprès du prestataire de la référence, du statut, du montant, de la devise et des identifiants de facture/demande/tentative. Un retour navigateur « succès » n’est pas une preuve de paiement.
- Solde revérifié avant de lancer la carte. Un changement de solde incompatible bloque le lien.
- Les chèques reçus mais non encaissés ne permettent pas de marquer une facture comme payée.
- Réessayer un envoi de courriel en échec conserve la même demande et ignore les destinataires déjà traités.

## Implémentation et exploitation

Les demandes et références de tentatives sont conservées dans `partial_payment_requests`, dans les métadonnées existantes de la facture. **Aucune migration de base nécessaire.** Le verrou de facture sérialise création, annulation et rapprochement. Une transaction CB confirmée utilise la catégorie `INVOICE_RANGE_PARTIAL_PAYMENT` et ne remplace pas la référence du paiement intégral.

La configuration existante du prestataire, du secret webhook, de l’expéditeur et de `FRONTEND_BASE_URL` est réutilisée. Déployer le frontend et le backend ensemble. Aucune clé de production n’est nécessaire pour les tests automatisés.

Les états `REVIEW` / `CREATING` persistants nécessitent de vérifier la référence auprès du prestataire avant toute relance ; ne pas supprimer ces marqueurs pour contourner la protection contre un double encaissement. L’échec d’un reçu est tracé dans `receipt_error` et le journal des communications ; une nouvelle notification bancaire ou consultation du lien déjà payé réessaie le reçu sans répéter la transaction.

Les factures réparties entre responsables conservent leurs parts de paiements antérieurs lors du paiement partiel CB. Leur rapprochement manuel ultérieur reste soumis au fonctionnement existant de la répartition familiale ; la clôture automatique lors de la remise d’espèces ajoutée ici concerne les factures non réparties.

## Vérifications

- `backend/tests/test_invoice_partial_payments.py` : validation, métadonnées, signatures, montants PSP ; intégration PostgreSQL pour le scénario 1 096 → 396 → 700, règlement ultérieur en espèces, chèques non encaissés, échecs, duplication concurrente, réessai, annulation, répartition familiale et reçu partiel.
- Les tests PostgreSQL exigent `PARTIAL_PAYMENT_TEST_DATABASE_URL` et refusent une base dont le nom n’est pas `partial_payment_test`. Utiliser exclusivement une base jetable isolée. Les prestataires et envois de courriel sont simulés.
- Régressions : `test_invoice*.py`, `test_payment*.py`, contrôles TypeScript, script `frontend/scripts/test-invoice-partial-payment.mjs`.
- Test navigateur local : ouverture depuis Factures, calcul immédiat 396 / 700, refus du montant total et des décimales supplémentaires, état pendant traitement, erreur d’envoi réessayable et annulation.

Validation locale du 31 août 2026 : 29 tests ciblés réussis, régressions des factures/documents/paiements réussies, TypeScript et build Next.js de production réussis. Les appels au prestataire restent simulés : aucun débit ni test bancaire en production. Le navigateur signale également un avertissement préexistant sur un autre formulaire de la fiche client (`target="_blank"` avec une action serveur), sans bloquer ce parcours.

Cette implémentation n’effectue aucun envoi client, débit réel ou déploiement à elle seule.
