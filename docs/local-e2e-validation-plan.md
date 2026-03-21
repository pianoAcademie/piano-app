# Recette locale E2E

Cette recette part du principe que la base locale a ete nettoyee avec :

```bash
cd "/Users/macair_jff/Documents/Appli resa/app"
export COMPOSE_PROJECT_NAME=piano-app
docker compose exec -T backend python /app/scripts/purge_local_smoke_data.py --apply
```

Objectif : valider le parcours complet a partir de vos activites reelles, depuis la creation des creneaux jusqu'a la facturation finale.

## Prerequis

- Au moins 1 activite collective presentielle creee par vos soins
- Au moins 1 activite en ligne creee par vos soins
- Au moins 1 produit facturable
- Au moins 1 kit facturable
- 1 catalogue de prix actif
- 1 type de devis actif
- Templates email/SMS configures dans `Admin > Config > Messagerie`

## Cas de test

### TC01 - Creation d'un creneau recurrent

- But : verifier la creation d'une serie simple
- Etapes :
  1. Creer un creneau hebdomadaire sur une activite collective
  2. Sauvegarder la serie
  3. Ouvrir la vue mois et la vue agenda
- Attendu :
  - la serie apparait dans les deux vues
  - la capacite est correcte
  - le professeur, le lieu et l'activite sont bien affiches

### TC02 - Heure locale fixe et changement d'heure

- But : verifier qu'un cours reste a la meme heure locale
- Etapes :
  1. Creer ou modifier une serie couvrant un passage heure d'hiver / heure d'ete
  2. Cocher `Heure locale fixe`
  3. Verifier les occurrences avant et apres le changement d'heure
- Attendu :
  - un cours a `18:00` reste a `18:00` heure locale
  - la vue mois reste alignee du dimanche au samedi

### TC03 - Capacite et creneau plein

- But : verifier la protection contre le surbooking
- Etapes :
  1. Remplir un creneau jusqu'a sa capacite
  2. Tenter une nouvelle affectation manuelle
- Attendu :
  - le BO bloque l'affectation supplementaire
  - le message est explicite

### TC04 - Intake simple avec matching direct

- But : verifier l'ingestion et la proposition directe
- Etapes :
  1. Soumettre un intake correspondant a un creneau clairement disponible
  2. Ouvrir l'intake dans le BO
- Attendu :
  - l'intake est normalisee
  - une proposition pertinente est affichee
  - l'arbitrage peut etre enregistre avec confirmation

### TC05 - Intake multi-propositions et recalcul

- But : verifier le recalcul des suggestions
- Etapes :
  1. Soumettre un intake avec plusieurs creneaux compatibles
  2. Selectionner `Aucune selection`
  3. Enregistrer l'arbitrage
  4. Corriger l'activite ou la formule dans `Corriger / completer`
  5. Revenir dans le panneau d'arbitrage
- Attendu :
  - aucune proposition ne reste retenue automatiquement
  - les suggestions sont recalculees sur la base de la nouvelle activite

### TC06 - Intake bloquee

- But : verifier le comportement en absence de creneau pertinent
- Etapes :
  1. Soumettre un intake sans creneau compatible
  2. Ouvrir l'intake
- Attendu :
  - le blocage est distingue d'un warning
  - la generation du devis est empechee

### TC07 - Generation du devis brouillon

- But : verifier la creation du devis a partir de l'intake
- Etapes :
  1. Depuis une intake arbitree, creer le devis brouillon
  2. Ouvrir le devis
- Attendu :
  - les informations parent/enfant/adulte sont reprises
  - les lignes facturees sont pre-remplies
  - les activites planifiees correspondent au snapshot du devis

### TC08 - Quantites facturees vs quantites planifiees

- But : verifier la coherence commerciale
- Etapes :
  1. Ouvrir `Lignes facturees`
  2. Comparer `Qt facturee` et `Qt planifiee`
  3. Modifier la quantite
- Attendu :
  - le prix unitaire reste stable
  - le total de ligne est recalcule
  - l'action `Aligner la quantite sur le planning` fonctionne

### TC09 - Envoi du devis par email et SMS

- But : verifier l'envoi client
- Etapes :
  1. Choisir un template email
  2. Si mobile renseigne, cocher `Envoyer aussi un SMS`
  3. Envoyer le devis
- Attendu :
  - le lien public et le PDF public sont corrects
  - un log email est cree
  - un log SMS est cree si active
  - le template choisi est bien celui utilise

### TC10 - Interface publique du devis

- But : verifier le parcours prospect
- Etapes :
  1. Ouvrir la page publique
  2. Verifier le rendu du document
  3. Utiliser les boutons d'action
- Attendu :
  - les blocs visibles/masques sont cohérents
  - les informations de prix et d'expiration sont correctes

### TC11 - Approbation publique

- But : verifier l'approbation par le prospect
- Etapes :
  1. Approuver le devis sur la page publique
  2. Revenir dans le BO
- Attendu :
  - le statut client passe a `Valide`
  - l'email de confirmation d'approbation est envoye si configure
  - le suivi des communications journalise bien l'action

### TC12 - Refus public

- But : verifier le rejet par le prospect
- Etapes :
  1. Rejeter le devis sur la page publique
  2. Revenir dans le BO
- Attendu :
  - le statut client passe a `Refuse`
  - l'email de confirmation de rejet est envoye si configure

### TC13 - Demande de modification publique

- But : verifier le retour prospect
- Etapes :
  1. Faire une demande de modification sur la page publique
  2. Consulter le BO
- Attendu :
  - la demande est visible cote admin
  - l'email de confirmation est envoye si configure

### TC14 - Restauration admin sans notifier

- But : corriger une action publique effectuee par erreur
- Etapes :
  1. Depuis le BO, restaurer l'etat precedent d'un devis approuve/refuse/modification demandee
- Attendu :
  - le devis revient a l'etat precedent
  - aucun email n'est renvoye au prospect

### TC15 - Relance automatique avant expiration

- But : verifier le job de relance
- Etapes :
  1. Configurer le template de relance et l'heure locale d'execution
  2. Positionner un devis a moins de 24h de l'expiration
  3. Laisser tourner le worker planifie ou forcer un passage
- Attendu :
  - un email de relance est envoye une seule fois
  - la communication apparait dans le journal

### TC16 - Annulation automatique

- But : verifier l'expiration puis l'annulation automatique
- Etapes :
  1. Configurer l'annulation automatique et son template
  2. Laisser depasser l'expiration d'un devis non valide
- Attendu :
  - le statut du devis bascule vers annule
  - la notification d'annulation part si activee

### TC17 - Transformation reussie en inscription

- But : verifier la transformation metier complete
- Etapes :
  1. Partir d'un devis approuve avec creneau encore disponible
  2. Lancer la transformation
- Attendu :
  - recontrole de capacite juste avant execution
  - creation du client cible si necessaire
  - creation des bookings sur les creneaux live
  - creation des charges / abonnements / produits / kits attendus
  - statut d'integration coherent

### TC18 - Transformation bloquee car creneau indisponible

- But : verifier la protection entre devis envoye et integration finale
- Etapes :
  1. Remplir le creneau vise apres emission du devis
  2. Relancer la transformation
- Attendu :
  - la transformation echoue proprement
  - rien n'est cree
  - le message indique clairement que le blocage vient du live

### TC19 - Rollback de transformation

- But : verifier la reversion admin
- Etapes :
  1. Realiser une transformation complete
  2. Lancer le rollback admin
- Attendu :
  - les bookings crees par la transformation sont supprimes
  - les charges / abonnements crees par la transformation sont retires
  - le devis revient dans un etat reexploitable

### TC20 - Facturation finale

- But : verifier la sortie finance
- Etapes :
  1. Partir d'une inscription transformee
  2. Verifier les lignes clients, abonnements, produits et kits
  3. Generer ou controler la facturation finale selon le mode utilise
- Attendu :
  - les montants attendus se retrouvent bien en finance
  - aucune ligne smoke/demo ne pollue les ecrans
  - la coherence entre planning, devis et finance est conservée

## Resultat attendu de la purge locale

Apres purge, il ne doit plus rester :

- d'activites `Smoke` ou `TYPEFORM_DEMO`
- de sessions `Smoke`
- d'intakes demo `demo_*`
- de devis/demo seeds `piano-academie.test`
- de communications demo/test

Les activites creees manuellement par vos soins doivent rester intactes.
