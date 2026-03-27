# Synthese Typeform 2026 et cas de tests Intake

Objectif : transformer les demandes reelles recues via Typeform en un jeu d'intakes local, rejouable dans le BO pour valider :

- `Intake`
- `Creation du devis`
- `Transformation du devis`
- `Facturation`

Les chiffres ci-dessous viennent des 8 exports CSV fournis.

## Vue d'ensemble

- Volume total analyse : `743` reponses
- Segments observes :
  - `Bar-le-Duc adultes`
  - `Bar-le-Duc eveil`
  - `Bar-le-Duc enfants`
  - `Paris eveil / initiation`
  - `Paris enfants`
  - `Paris adultes`
  - `Paris selection de creneaux / profils avances`

## Tendances fortes

### Bar-le-Duc adultes

- Formulaire `it6d2RCL`
- `38` reponses
- Demande dominante : `cours collectif` a l'ecole de Bar-le-Duc
- Engagement le plus frequent : `annuel`, puis `par 10 cours`
- Paiement recurrent dominant : `Carte Bleue mensuelle`

### Bar-le-Duc eveil

- Formulaire `lxcPknI5`
- `8` reponses
- Demande tres concentree sur `samedi 10h`
- Population tres jeune : naissances `2022`
- Paiement surtout `CB en 1 fois`

### Bar-le-Duc enfants

- Formulaire `NASR979B`
- `47` reponses
- `22` reinscriptions sur `47`
- Demande quasi uniforme : `cours collectif de 1h`
- Paiement dominant : `CB mensuelle`
- Solfege tres present, surtout `debutant / niveau 1 / niveau 2`

### Paris eveil / initiation

- Formulaires `MzQIz2u9` et `CQSkTglB`
- `124` reponses cumulees
- Sites dominants : `Pompe`, puis `Richelieu`, puis `Assas`
- Eveil : formule `annuelle` majoritaire, avec un vrai besoin `carnet 5 cours`
- Paiement varie : `CB 1 fois`, `virement`, `cheque en 4 fois`

### Paris enfants

- Formulaire `qFdJ47yB`
- `223` reponses
- Sites dominants : `Pompe`, `Richelieu`, `Scheffer`, `Assas`
- Offre dominante : `cours collectif a l'ecole`
- Options frequentes :
  - `solfege`
  - `Pass Recup`
  - `2e cours collectif`
  - `Classes Booster`
- `55` reinscriptions sur `223`

### Paris adultes

- Formulaire `uazrOkar`
- `246` reponses
- Lieux demandes : `Pompe`, `Scheffer`, `Richelieu`, `Assas`, `Domicile`
- Offre dominante : `cours collectif a l'ecole`
- Paiements les plus frequents : `CB 1 fois`, `Virement 1 fois`, `Cheque 4 fois`
- Options observees : `2e cours`, `MasterClass`, `Allo Piano`, `Pass Recup`

### Paris selection explicite de creneaux

- Formulaire `xbWmPSsx`
- `57` reponses
- Forte logique de selection par `site / creneau`
- Lieu majoritaire : `Scheffer / Pompe`

## Perimetre seed local actuel

Le seed local a ete refait avec une contrainte stricte : `aucune activite Typeform n'est creee`.

Le script s'appuie uniquement sur les activites deja presentes dans ton catalogue local :

- `ACT_EVEIL_MUSICAL_98E099`
- `PIANO_GROUP_ONSITE_1H`
- `PIANO_GROUP_ONLINE_1H`
- `ACT_MASTERCLASS_D84DC5`

En consequence :

- les demandes `Paris eveil / initiation`
- les demandes `Paris enfants`
- les profils `selection de creneaux / masterclass`

sont bien seedes localement.

En revanche, les demandes `Bar-le-Duc` et `adultes` restent seulement synthétisées dans ce document. Elles ne sont pas seedées tant qu'il n'existe pas dans ton environnement local des activites et des creneaux deja crees par toi pour ces segments.

## Jeu de cas de tests retenu

Le script [seed_realistic_typeform_intakes_2026.py](/Users/macair_jff/Documents/Appli%20resa/app/backend/scripts/seed_realistic_typeform_intakes_2026.py) genere `8` intakes sur le catalogue existant.

### Cas 1 - Paris eveil Pompe mercredi 10h arbitre

- Source : `MzQIz2u9`
- Activite utilisee : `ACT_EVEIL_MUSICAL_98E099`
- Statut attendu : `READY_FOR_DRAFT_QUOTE`
- But : tester directement `devis -> transformation -> facturation`

### Cas 2 - Paris eveil multi-creneaux Pompe

- Source : `MzQIz2u9`
- Activite utilisee : `ACT_EVEIL_MUSICAL_98E099`
- Statut attendu : `MATCHING_REQUIRED`
- But : tester l'arbitrage BO avant creation du devis

### Cas 3 - Paris initiation Richelieu arbitree

- Source : `CQSkTglB`
- Activite utilisee : `ACT_EVEIL_MUSICAL_98E099`
- Statut attendu : `READY_FOR_DRAFT_QUOTE`
- But : tester un cas initiation/eveil deja arbitre

### Cas 4 - Paris enfant presentiel Pompe arbitre

- Source : `qFdJ47yB`
- Activite utilisee : `PIANO_GROUP_ONSITE_1H`
- Statut attendu : `READY_FOR_DRAFT_QUOTE`
- But : tester le cas nominal enfant presentiel

### Cas 5 - Paris enfant online arbitre

- Source : `qFdJ47yB`
- Activite utilisee : `PIANO_GROUP_ONLINE_1H`
- Statut attendu : `READY_FOR_DRAFT_QUOTE`
- But : tester le cas nominal enfant online

### Cas 6 - Paris enfant presentiel matching

- Source : `qFdJ47yB`
- Activite utilisee : `PIANO_GROUP_ONSITE_1H`
- Statut attendu : `MATCHING_REQUIRED`
- But : tester un matching manuel sur le collectif enfant

### Cas 7 - MasterClass selection manuelle Scheffer

- Source : `xbWmPSsx`
- Activite utilisee : `ACT_MASTERCLASS_D84DC5`
- Statut attendu : `MATCHING_REQUIRED`
- But : tester un profil avance de selection de creneaux

### Cas 8 - MasterClass bloquee dimanche 07h

- Source : `xbWmPSsx`
- Activite utilisee : `ACT_MASTERCLASS_D84DC5`
- Statut attendu : `BLOCKED`
- But : verifier un blocage net sans creation de devis

## Commande de seed

Depuis le projet :

```bash
cd "/Users/macair_jff/Documents/Appli resa/app"
export COMPOSE_PROJECT_NAME=piano-app
docker compose exec -T backend python /app/scripts/seed_realistic_typeform_intakes_2026.py
```

Le script affiche :

- les `8` intakes crees
- leur `statut`
- leur `intake_id`
- leur URL BO locale
- `typeform_activity_count: 0`

Ce dernier point confirme qu'aucune activite `TF_DEMO_*` ou `TF_REALISTIC_2026_*` n'a ete recreee.

## Ordre de recette conseille

1. Commencer par un cas `READY_FOR_DRAFT_QUOTE`
2. Generer le devis brouillon
3. Verifier les lignes et le snapshot planning
4. Transformer
5. Controler la facturation
6. Rejouer avec un cas `MATCHING_REQUIRED`
7. Finir avec le cas `BLOCKED`
