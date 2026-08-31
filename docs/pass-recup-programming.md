# Programmer un rattrapage avec un Pass Récup

## Parcours gestionnaire

1. Dans Planning → cours d'origine → Présences, enregistrer l'absence signalée en
   « Absent excusé ». L'annulation par le parent dans les délais peut également
   ouvrir le droit. Un crédit du pass est consommé à cette étape, pas à la réservation.
2. Ouvrir Clients → fiche de l'enfant (ou du parent payeur) → Réservations.
3. Dans « Pass Récup et crédits de rattrapage », repérer **le cours manqué et sa date**.
4. Cliquer « Programmer ce rattrapage ». Choisir la période de recherche, le lieu,
   puis une séance disponible. La recherche porte sur 31 jours ; changer la date
   de départ pour consulter une autre période.
5. Vérifier le récapitulatif : **supplément 0**, puis « Confirmer ce rattrapage ».
6. Le cours manqué et son remplacement apparaissent ensemble dans l'historique.

Ne pas utiliser « Déplacer » ou l'inscription classique pour contourner un refus.
Les droits de modification du planning sont nécessaires côté serveur.

## Garanties

- Une absence précise, un crédit déjà consommé, un remplacement actif au maximum.
  Une répétition de la même confirmation est idempotente.
- Forfait actif « Année 2026-2027 », achat du pass rattaché au même enfant et au
  même forfait, absence encore signalée, créneau dans la validité du pass.
- Cours collectif de même durée et même activité. Une activité en ligne différente
  doit partager explicitement le type de crédit pédagogique et le service de
  l'activité d'origine. Le Pass Récup Online interdit tout créneau présentiel.
  Les essais, activités individuelles et incompatibles ne sont pas proposés.
  Si le catalogue ne relie pas les activités en ligne, il faut vérifier cette
  configuration ; aucune équivalence tarifaire n'est déduite du prix ou du nom.
- Les places, le public autorisé, les horaires et les délais sont revérifiés à
  la confirmation ; pas de surbooking ni de mise en attente implicite.
- Prix/remises du cours d'origine conservés. Son absence ne génère pas d'avoir
  d'annulation automatique lorsqu'elle est couverte par ce pass. Le remplacement
  a un montant nul verrouillé et reste visible dans Réservations, sans nouvelle
  ligne de vente dans Compte. Aucun changement des devis ou factures existants.
- Un avoir d'annulation déjà émis bloque la programmation pour vérification
  comptable, sans modifier cet avoir.
- Aucun email immédiat de confirmation n'est envoyé par ce bouton. Les rappels
  habituels du cours sont programmés selon les réglages existants.
- Une annulation du remplacement libère le même droit, sans consommer un autre
  crédit. Corriger la présence d'origine est bloqué tant que son remplacement
  est réservé ; annuler d'abord ce dernier si la présence était erronée.

## Portée de la livraison

Pas de migration, pas de modification en masse des anciens rattrapages ou
factures. Les nouveaux droits et les droits existants explicitement programmés
utilisent le traitement comptable protégé. L'ancien parcours client réutilise
les mêmes contrôles lors d'une réservation avec rattrapage ; le calcul d'un
devis ou d'un cours annuel ordinaire n'est jamais transformé en séance gratuite.
