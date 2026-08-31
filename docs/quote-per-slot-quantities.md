# Quantités des devis : rattachement par créneau

La synchronisation des lignes issues d'intake utilisait le total par activité
pour une ligne principale dépourvue de clé automatique. Un second cours de la
même activité était ainsi inclus dans cette ligne puis facturé séparément.

Le résolveur `services/quotes/line_sessions.py` utilise les clés explicites,
les clés automatiques et les identifiants de ligne. Pour un ancien identifiant
devenu obsolète, il n'accepte que le groupe restant unique pour une seule ligne
restante sans clé explicite. Aucun rapprochement par ordre, tarif ou quantité.
Les cas ambigus échouent en HTTP 409 avant modification des quantités.

La clé trouvée est conservée en métadonnées de ligne : la recréation des lignes
par l'éditeur ne change plus le rattachement. La génération documentaire
préserve cette clé explicite. Le calcul des échéances mensuelles réutilise les
séances de chaque ligne. Une ligne manuelle conserve sa quantité et son tarif.

Tests : `test_quote_planned_quantity_sync.py`, `test_quote_line_sessions_postgres.py`
(PostgreSQL isolé uniquement), régressions des documents, de l'intégration,
des devis annuels et de leurs tarifs. Cas Kenza : 32 × 38 € + 31 × 32 € + 305 €
de produits = 2 513 €, au lieu de 3 691 €. Les 89 séances du planning ne changent pas.

Le correctif logiciel ne réécrit pas automatiquement les dossiers existants.
La régularisation d'un dossier doit être ciblée, sauvegardée, auditée et
précédée d'une simulation ; aucun devis envoyé/accepté ne doit être modifié
sans traitement métier approprié.
