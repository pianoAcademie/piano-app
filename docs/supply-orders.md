# Commandes fournisseurs et réception

Dans **Produits → Réapprovisionnement**, enregistrer une commande déjà passée avec
son lieu, sa date de livraison prévue et les quantités de chaque produit. Cela ne
contacte pas le fournisseur, ne crée aucun paiement et n'ajoute aucun stock.

Un produit absent du catalogue peut être saisi sous son nom exact. Avant réception,
créer sa fiche produit avec les données commerciales appropriées puis la choisir
dans la réception. Ne pas confondre les cahiers de travail et les cahiers de solfège.

À la livraison complète, ouvrir **Réceptionner cette commande**, saisir la date
réelle et confirmer toutes les quantités. La réception crée un mouvement d'achat
par ligne au lieu choisi. Ne pas saisir aussi une entrée de stock manuelle pour
ces mêmes quantités. Les livraisons partielles ne sont pas prises en charge : ne
pas confirmer une réception complète si des articles restent à livrer.

Les répétitions d'une même soumission et d'une réception sont idempotentes, y
compris en concurrence. Une réception est atomique : aucun mouvement partiel
n'est conservé si une ligne échoue. L'annulation du suivi n'affecte pas le stock et
ne transmet aucune annulation au fournisseur. Toutes ces opérations sont admin.

## Vérifications

- Migration `20260830_0229`, ajout de deux tables uniquement, après `0228`.
- Tests PostgreSQL : définir `SUPPLY_ORDER_TEST_DATABASE_URL` vers une base
  **jetable et migrée**, puis lancer `python -m unittest tests.test_supply_orders -v`
  depuis `backend`. Le test de concurrence conserve des fixtures dans cette base.
- `python3 backend/scripts/check_alembic_chain.py`
- `docker compose build backend frontend`

La commande Richelieu du 30/08/2026 est enregistrable avec
`backend/scripts/record_supply_order_richelieu_20260830.py` (simulation par défaut,
`--apply` pour valider). Son identifiant fixe évite les doublons ; le script vérifie
les références et que le stock ne change pas. Il n'enregistre pas de réception.
