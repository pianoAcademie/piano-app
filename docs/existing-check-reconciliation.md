# Rattacher des chèques existants

Dans **Clients → Compte**, ouvrir le crayon d'un chèque reçu ou déposé,
puis utiliser **Rattacher les chèques existants à une facture** en haut de la
fenêtre. Sélectionner une facture émise et cocher les chèques concernés.
Le chèque ouvert est présélectionné ; les autres nécessitent une sélection
explicite. Confirmer le rattachement avec le bouton dédié.

Cette opération est indépendante du formulaire de modification situé dessous.
Elle ne modifie ni le montant, ni le statut, ni les dates des chèques ; elle ne
crée aucun paiement et n'envoie aucun message. Le total de la facture et ses
lignes figées sont conservés. La couverture complète suspend les relances,
mais la facture ne devient pas payée avant l'encaissement.

Le serveur contrôle le compte, l'entité juridique, la devise, le statut et le
solde non couvert. Il refuse les chèques déjà affectés ailleurs et les factures
réparties entre payeurs. Les liens de paiement actifs doivent être traités avant
le rattachement. Les écritures et la facture sont verrouillées pendant
l'opération ; une répétition de la même demande ne compte pas deux fois un chèque.
Une note interne conserve la liste des écritures rattachées et l'administrateur.
