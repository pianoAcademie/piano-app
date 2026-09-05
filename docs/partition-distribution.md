# Distribution des partitions à Paris

## Parcours

- Professeur : `/prof/partitions`, lien depuis son accueil. Choisir la semaine ; les besoins proviennent des réservations du planning de production, avec remplacement professeur pris en compte. Un élève et une référence ne sont comptés qu'une fois. Les partitions déjà remises ne sont pas à reprendre.
- Une partition inconnue apparaît « À définir ». Le professeur choisit la référence avant de préparer son retrait.
- Le professeur demande les quantités retirées à Richelieu. L'administration confirme les quantités réellement données sur `/admin/partition-distribution`, accessible depuis Produits. Une demande seule ne modifie pas le stock.
- Le professeur peut confirmer son propre retrait en saisissant la quantité réellement récupérée (champ vide, sans validation automatique de la quantité demandée). L'administration peut également confirmer le retrait ; elle seule valide les retours. La confirmation transfère le stock de Richelieu vers le professeur ; le stock global ne baisse pas.
- Le professeur confirme la remise à chaque élève. Cette action consomme son stock, date la remise et actualise le suivi pédagogique. Elle ne crée aucune facture.
- Si la référence change avant remise, sélectionner la partition réellement remise. L'ancien exemplaire reste chez le professeur jusqu'à son retour. Les retours sont confirmés par l'administration.

## Contrôles

Les confirmations sont rejouables sans double mouvement. Les stocks insuffisants, remises répétées et retraits au nom d'un autre professeur sont bloqués. L'ancien bouton de remise produit ne peut pas redébiter une remise déjà enregistrée ici. Toutes les demandes en attente restent affichées, même au-delà des 200 derniers mouvements historiques.

Une progression terminée prépare la partition suivante sans prétendre qu'elle a déjà été remise physiquement.

## Mise en service

Appliquer la migration `20260905_0241` avant le démarrage du code mis à jour. Vérifier l'inventaire réel à Richelieu et les références élèves avant les premiers retraits. Aucun historique de livraison n'est inventé par la migration. Pour les exemplaires déjà emportés avant la mise en service, réconcilier l'inventaire avant de saisir des retraits afin de ne pas les décompter deux fois.

## Vérification locale

Migration aller/retour vérifiée sur une base PostgreSQL isolée. Les tests de distribution s'exécutent avec `PARTITION_TEST_DATABASE_URL` ; ils annulent leurs données à la fin de chaque test. Ne jamais les pointer vers la production.

## Déploiement du 5 septembre 2026

Correctif `e3e195cd` appliqué sélectivement sur la production, en préservant le correctif de réorganisation `6744e88e` déployé le même matin. Les sources correspondantes sont réunies dans le commit de fusion `5d86ab4f`.

Sauvegarde préalable : `/home/ubuntu/deploy-backups/partition-distribution-e3e195cd` (sources, export PostgreSQL et références des anciennes images). Images de retour arrière : `piano-partition-rollback-backend:e3e195cd` et `piano-partition-rollback-frontend:e3e195cd`. Ne pas restaurer la base pour un simple retour arrière applicatif : la migration ajoute une table compatible avec l'ancien code.

Les deux images ont été construites avant remplacement des conteneurs. Base de données, Redis et workers de notifications laissés en service. Migration `20260905_0241` appliquée, schéma d'authentification contrôlé. Compilation Next.js réussie ; 30 tests combinés partitions/réorganisation réussis. Contrôle en lecture seule du tableau sur la production : semaine du 7 septembre, 343 besoins et aucun mouvement créé. API saine, connexion publique HTTP 200 et route professeur protégée par redirection d'authentification.
