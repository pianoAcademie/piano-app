# Programme de parrainage et depots de cheques

## Perimetre

Ce lot ajoute :

- la detection du parrain depuis un champ libre Typeform ;
- le matching automatique quand il est suffisamment fiable ;
- la validation manuelle du parrain depuis les intakes et le tableau parrainages ;
- des montants configurables par categorie : Paris, Bar-le-Duc, en ligne, domicile ;
- la generation d'un avoir lorsque le filleul atteint le seuil d'encaissement configure ;
- les emails d'annonce et d'avoir ;
- un tableau de suivi des parrainages et un export CSV ;
- un menu dedie aux depots de cheques ;
- l'import CSV/XLSX de remises de cheques ;
- le passage par lot aux statuts cheque recu, cheque depose, puis encaisse.

## Regles metier a valider

- Paris regroupe Richelieu, Assas, Pompe et Scheffer.
- Video Call correspond a la categorie En ligne.
- Domicile a sa propre categorie.
- Bar-le-Duc a sa propre categorie.
- Le seuil par defaut est 50% de la facture annuelle.
- Un acompte seul ne declenche pas l'avoir.
- `CHECK_RECEIVED` ne compte pas comme encaissement.
- `CHECK_DEPOSITED` ne compte pas comme encaissement.
- `PAID`, `COMPLETED` et `SUCCEEDED` comptent comme encaissement.
- Pour les cheques en plusieurs fois et les CB mensuelles, l'avoir est genere quand le seuil d'encaissement est atteint.
- Un parrainage de soi-meme doit rester en revue manuelle.
- Les cas ambigus restent a valider manuellement.

## Checklist staging

- Deployer backend et frontend sur staging.
- Lancer `alembic upgrade head`.
- Verifier `alembic current`, attendu : `20260509_0108`.
- Se connecter en admin.
- Configurer le programme dans Admin > Configuration > Parrainage.
- Verifier les montants des quatre categories.
- Verifier le seuil d'encaissement.
- Verifier les emails d'annonce et d'avoir avec une adresse de test.
- Soumettre un Typeform avec un nom de famille parrain.
- Transformer le devis en inscription.
- Generer une facture annuelle.
- Enregistrer un paiement sous le seuil et verifier qu'aucun avoir n'est genere.
- Enregistrer un paiement atteignant le seuil et verifier que l'avoir est genere.
- Tester un cheque recu, puis depose, puis encaisse.
- Tester un import CSV de cheques.
- Tester un import XLSX de cheques.
- Tester une ligne importee avec un nom sur cheque different du client.
- Tester une ligne importee ambigue et verifier qu'elle reste non rapprochee.
- Exporter les parrainages.
- Exporter les cheques attendus.
- Telecharger le modele d'import cheques.
- Utiliser le bouton Tout recalculer sur les parrainages.

## Process conseille pour les cheques

- A la validation de l'inscription, saisir tous les cheques recus dans la fiche client avec le statut `CHECK_RECEIVED`.
- Verifier que la somme des cheques correspond au montant attendu sur la facture annuelle.
- Avant une remise bancaire, ouvrir Admin > Depots de cheques.
- Exporter les cheques attendus pour obtenir les `transaction_id`.
- Scanner les cheques et preparer le fichier CSV/XLSX avec au minimum `transaction_id` quand il est connu.
- Si le `transaction_id` n'est pas connu, renseigner le montant et le nom visible sur le cheque.
- Importer le fichier en action `Passer en deposes`.
- Traiter manuellement les lignes non rapprochees avant de refaire un import ou une selection par lot.
- Quand la banque confirme l'encaissement, passer les cheques concernes en `PAID`.
- Ne jamais utiliser `CHECK_DEPOSITED` comme preuve d'encaissement : l'avoir parrainage attend un vrai statut encaisse.

## Checklist production

- Prevenir l'equipe du nouveau process.
- Faire un backup DB juste avant deploiement.
- Deployer backend et frontend.
- Lancer `alembic upgrade head`.
- Verifier `alembic current`.
- Verifier `/health`.
- Verifier que les workers de notifications tournent.
- Verifier que le frontend utilise bien `npm ci` via le Dockerfile.
- Configurer ou confirmer les montants de parrainage.
- Faire un test reel limite avec une famille test ou interne.
- Surveiller les logs backend pendant les premiers imports Typeform et les premiers paiements.
- Surveiller les emails sortants.
- Controler les premiers avoirs crees dans les paiements clients.

## Rollback

Si le deploiement applicatif doit etre annule :

- redeployer l'image backend precedente ;
- redeployer l'image frontend precedente ;
- ne pas supprimer la table `referral_rewards` si des avoirs ont deja ete generes ;
- desactiver le programme via la configuration admin si le rollback code n'est pas immediat ;
- verifier les transactions `category=REFERRAL_CREDIT` avant toute correction manuelle.

Si aucun avoir n'a ete genere et qu'il faut revenir completement en arriere, la migration Alembic peut supprimer la table `referral_rewards` via downgrade. A eviter si des donnees de parrainage ont deja ete exploitees.

## Commandes de verification

```bash
docker compose run --rm backend alembic heads
docker compose run --rm backend alembic current
docker compose run --rm backend python -m pytest -q
docker compose build backend frontend
curl -fsS http://localhost:8000/health
```

## Risques connus

- `npm audit` signale encore Next/PostCSS. Le correctif propose impose Next 16.
- Une tentative Next 16 casse les signatures de route handlers ; la migration Next 16 doit rester un chantier separe.
- L'import Excel supporte `.xlsx`, pas l'ancien format `.xls`.
- Le matching par nom de cheque est volontairement prudent : en cas d'ambiguite, la ligne reste non rapprochee.
