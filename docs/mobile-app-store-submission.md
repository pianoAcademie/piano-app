# App Store and TestFlight submission draft

Objectif: preparer les informations necessaires a App Store Connect pour deux apps separees, sans publier publiquement avant stabilisation.

## Apps a creer dans App Store Connect

### Piano Academie Client

- Bundle ID: `com.pianoacademie.client`
- SKU suggere: `PA-CLIENT-IOS`
- Plateforme: iOS
- Distribution conseillee maintenant: TestFlight interne
- URL de support: `https://app.piano-academie.com/support`
- URL de confidentialite: `https://app.piano-academie.com/privacy`
- Categorie suggeree: Education
- Audience: familles, eleves adultes, responsables de compte

Description courte possible:

```text
L'espace mobile des eleves et familles Piano Academie pour consulter les cours, documents, paiements et messages utiles.
```

### Piano Academie Professeur

- Bundle ID: `com.pianoacademie.professeur`
- SKU suggere: `PA-PROF-IOS`
- Plateforme: iOS
- Distribution conseillee maintenant: TestFlight interne
- URL de support: `https://app.piano-academie.com/support`
- URL de confidentialite: `https://app.piano-academie.com/privacy`
- Categorie suggeree: Education
- Audience: professeurs et collaborateurs pedagogiques

Description courte possible:

```text
L'espace mobile des professeurs Piano Academie pour suivre le planning, les cours, les documents et les informations utiles.
```

## Captures a preparer

Pour TestFlight interne, les captures App Store ne sont pas bloquantes. Pour une soumission publique, preparer au minimum:

- iPhone 6.7 pouces: ecran de connexion, accueil client, planning client, document/paiement client.
- iPhone 6.7 pouces: accueil professeur, planning professeur, feuille de cours ou releve.
- iPad si l'app est declaree compatible iPad.

Les captures ne doivent pas montrer de vraies donnees client/professeur. Utiliser un compte de demonstration dedie.

## Confidentialite App Store Connect

La privacy native iOS declaree dans `PrivacyInfo.xcprivacy` couvre uniquement la couche native. Les labels App Store doivent decrire le service web affiche dans l'app.

Points probables a declarer selon les parcours actifs:

- Identifiants: nom, email, telephone si visible/utilise.
- Donnees de paiement: uniquement si l'app affiche ou traite des informations de paiement.
- Contenu utilisateur: messages, demandes, documents si actifs dans les portails.
- Donnees d'utilisation: uniquement si un outil d'analyse est actif.
- Diagnostics: uniquement si un outil de crash/reporting est actif.

A verifier avant soumission publique:

- Existence d'un outil analytics cote web.
- Existence d'un outil crash reporting cote mobile.
- Donnees exactes envoyees aux prestataires de paiement et de notification.
- Texte final de politique de confidentialite valide juridiquement.

## Regles Apple a surveiller

- Les cours physiques peuvent rester payes via le web ou les prestataires existants; l'achat in-app Apple n'est normalement pas requis pour des services physiques.
- Les liens de paiement externes doivent rester dans le cadre du service Piano Academie et ne pas vendre du contenu numerique autonome.
- L'app professeur ne doit pas exposer de donnees personnelles d'autres professeurs ou familles au-dela des droits deja geres par le portail.
- L'admin reste hors app mobile.

## Parcours TestFlight minimum

Avant d'inviter des testeurs externes:

- Connexion/deconnexion client.
- Connexion/deconnexion professeur.
- Ouverture PDF depuis l'app.
- Paiement ou redirection paiement depuis iPhone.
- Retour dans l'app apres paiement ou lien externe.
- Consultation planning client.
- Consultation planning professeur.
- Messages ou communications si disponibles.
- Gestion de session expiree.

## Decision conseillee

Rester en TestFlight interne jusqu'a stabilisation des releases devis/planning. Ouvrir TestFlight externe uniquement avec un petit groupe pilote en septembre, puis publier l'app client avant l'app professeur.
