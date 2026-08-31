# Réinscription et transparence tarifaire

## Utilisation

Dans **Devis → Lignes facturées**, le récapitulatif est toujours visible : quantité,
prix unitaire TTC, origine et montant de chaque prestation, remise, produit et
supplément, ajustement exceptionnel éventuel et total enregistré. Le PDF n'est pas
nécessaire pour contrôler ces montants.

Pour un ancien élève dont l'historique est dans l'ancien logiciel :

1. Ouvrir « Vérifier et calculer les remises annuelles ».
2. Choisir l'élève, la catégorie, le cours principal et la référence familiale.
3. Choisir « Réinscription — fidélité confirmée par l’administration » et renseigner
   le justificatif de réinscription ainsi que celui du calcul.
4. Si des remises manuelles existent, choisir explicitement de conserver toutes
   les lignes actuelles sans calcul automatique, ou de remplacer les remises listées.
5. Calculer l'aperçu, vérifier toutes les lignes et les totaux avant/après, puis confirmer.

La confirmation administrative est mémorisée par élève et saison, avec auteur,
date et justificatif. L'aperçu seul ne sauvegarde rien. La preuve de fidélité ne
se transmet pas aux frères/sœurs. Les règles de cumul restent celles du moteur
annuel existant. Le calculateur reste limité au forfait 2026-2027 en EUR ; le
récapitulatif des lignes est disponible pour les autres devis également.

Le remplacement nécessite une confirmation et ne cumule jamais silencieusement
les remises importées et automatiques. La conservation ne revalorise aucune ligne.
Les devis envoyés/acceptés restent verrouillés ; utiliser une révision.

## Garde-fous et livraison

- Un changement de statut de réinscription invalide le calcul des autres devis
  non envoyés du même élève et de la même saison.
- Le contrôle de génération compare les lignes + ajustements au total enregistré.
- La migration additive `20260831_0231` crée `annual_student_enrollments` sans
  recalculer de devis, réservation ou facture existante. Déployer la migration
  avant de servir le nouveau code backend.
- Aucun envoi, régularisation historique ou déploiement n'est effectué par ce changement.

Tests : PostgreSQL isolé (persistance, non-cumul, remplacement atomique,
cas 31 × 38 − 62 + 245 + 25 = 1 386 €, cohérence documentaire, migrations aller/retour),
tests documents et intégration tarifaire, compilation Next.js avec contrôle des types.

## Déblocage des migrations historiques

Les révisions 0215 à 0219 réutilisent la connexion Alembic dans un savepoint.
Les scripts conservent leur transaction autonome lorsqu'ils sont exécutés en CLI.
Leurs chemins « cible absente » ne chargent que les clés stables, afin de ne pas
demander les colonnes ajoutées plus tard dans l'historique. Les révisions déjà
appliquées ne sont pas rejouées lors du déploiement.

La validation comprend la reconstruction du schéma par migrations et 20 cas de
non-blocage sous verrou, commit, rollback et erreur, sur PostgreSQL isolé. Les
fixtures tarifaires respectent également les contraintes de ce schéma migré.
