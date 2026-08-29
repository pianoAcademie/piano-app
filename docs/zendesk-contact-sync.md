# Synchronisation des contacts Zendesk

La synchronisation est strictement à sens unique : Piano Académie écrit dans Zendesk, sans importer les utilisateurs, tickets ou notes Zendesk dans l'application.

## Périmètre

- Les clients adultes/responsables et les prospects adultes deviennent des utilisateurs finaux Zendesk.
- Les enfants ne deviennent jamais des utilisateurs Zendesk.
- La fiche de l'adulte reçoit des champs privés visibles par les agents : indication adulte élève, formules en cours de l'adulte, enfants liés, créneaux futurs, lieux, statut et lien vers la fiche Piano Académie.
- Les adresses e-mail secondaires et les numéros de téléphone valides sont ajoutés comme identités pour permettre la reconnaissance des e-mails et appels entrants.
- Un numéro partagé par plusieurs adultes n'est pas envoyé comme identité. Le conflit est consigné dans le suivi des jobs.

## Exploitation

Le workflow GitHub Actions `Synchroniser les contacts Zendesk` propose deux modes :

- `dry-run` contrôle le périmètre et la connexion sans modifier Zendesk ;
- `apply` crée ou met à jour les champs et utilisateurs Zendesk.

Le premier lancement `apply` active le job périodique. Ensuite, les changements sont synchronisés toutes les 15 minutes et un contrôle complet est effectué quotidiennement. Le workflow de déploiement exécute seulement un contrôle à blanc en lecture seule.

Les secrets `ZENDESK_SUBDOMAIN`, `ZENDESK_ADMIN_EMAIL` et `ZENDESK_API_TOKEN` sont injectés dans le fichier `.env` protégé du VPS par le déploiement. Ils ne doivent jamais être écrits dans le dépôt.
