# Piano Academie - V1 locale (Docker Compose)

## Prerequis
- Docker Desktop (Compose v2)

## Demarrage
```bash
cd /Users/macair_jff/Documents/Appli\ resa/app
docker compose up -d --build
docker compose ps
```

Services:
- Backend API: http://localhost:8000
- Frontend Next.js: http://localhost:3000
- PostgreSQL: localhost:5432

## Checks rapides
```bash
curl -s http://localhost:8000/health
curl -I http://localhost:3000/login
```

## Smoke test complet V1
Le smoke test execute un parcours complet:
- auth roles (admin/prof/client)
- profil client
- achat plan + contraintes metier (anti double abonnement mensuel, anti nouveau pack si credits restants)
- reservation + waitlist + annulation client
- attendance
- reminders
- auto-cancel
- pricing + TVA admin
- reports
- payouts

Commande:
```bash
docker compose exec -T backend python scripts/smoke_v1.py
```

Resultat attendu:
```json
{"ok": true, ...}
```

Smoke test cible agenda admin (portee de serie):
```bash
docker compose exec -T backend python scripts/smoke_admin_series.py
```

Resultat attendu:
```json
{"ok": true, "scenario": "admin_series_scope", ...}
```

Smoke test cible collaborateurs/professeurs:
```bash
docker compose exec -T backend python scripts/smoke_collaborators_v1.py
```

Resultat attendu:
```json
{"ok": true, "scenario": "collaborators_v1", ...}
```

## Durcissement ajoute
- Backend: logs JSON structures + request id (`X-Request-ID`) + duree de requete.
- Frontend: timeout configurable des appels backend (`BACKEND_TIMEOUT_MS`).
- CI GitHub Actions: `.github/workflows/ci.yml` execute `docker compose up`, le smoke test et les checks frontend.

## Vue agenda client
Le dashboard client propose maintenant une vue agenda des cours avec:
- vue mois
- vue semaine
- vue jour
- filtres combines: type de cours, lieu, fuseau horaire, date de reference

## Interface admin agenda
URL: `http://localhost:3000/admin`

Fonctionnalites V1:
- vue par lieu (lecture par defaut)
- affichage reservations/capacite + statut du cours
- bascule Lecture / Edition
- en mode Edition: creation, modification, annulation et suppression de cours
- portee d'action sur les cours recurrents: ce creneau, serie future, toute la serie
- deplacement rapide d'horaires (-15m, +15m, +1h, +1j)
- agenda mois / semaine / jour
- filtres type de cours / lieu / professeur / statut / fuseau horaire

Note:
- le formulaire admin de creation utilise des champs date/heure saisis en UTC.

## Interface admin collaborateurs
URL: `http://localhost:3000/admin/professors`

Fonctionnalites V1:
- creation d'un collaborateur/professeur depuis l'admin (sans email envoye a la creation)
- fiche collaborateur: email, prenom, nom, telephone, lien Zoom, langues parlees, role, mode coach
- activation / desactivation du collaborateur
- envoi d'un email d'activation uniquement lors du passage inactif -> actif
- edition des droits d'acces (planning, adherents, abonnements, paiements, administration)
- configuration des taux horaires par type de cours
- acces au planning du professeur (vue jour/semaine/mois)

## Espace professeur
URL: `http://localhost:3000/prof`

Fonctionnalites V1:
- connexion professeur (compte actif)
- consultation du profil professeur
- consultation du planning personnel selon autorisations
- blocage automatique si droits planning retires

## Deploiement VPS (GitHub Actions)
Workflow: `.github/workflows/deploy-vps.yml`

Le workflow deploie automatiquement sur VPS lors d un `push` sur `main/master` ou manuellement via `workflow_dispatch`.

Avant de deployer les changements parrainage + depot de cheques, suivre la note de release:
`docs/referral-and-check-deposits-release.md`.

Secrets GitHub requis:
- `VPS_HOST`: IP ou domaine du serveur (ex: `83.228.220.74`)
- `VPS_USER`: utilisateur SSH (ex: `ubuntu`)
- `VPS_SSH_KEY`: cle privee SSH du compte de deploiement (format OpenSSH, sans passphrase interactive)
- `VPS_PATH`: dossier projet sur le serveur (ex: `/home/ubuntu/piano-app`)
- `VPS_PORT`: port SSH (optionnel, `22` par defaut)
- `VPS_KNOWN_HOSTS`: sortie de `ssh-keyscan -H <host>` (optionnel mais recommande)

Etapes du workflow:
- sync du code vers le VPS via `rsync`
- `docker compose up -d --build`
- healthchecks backend/frontend en local serveur (`127.0.0.1:8000` et `127.0.0.1:3000`)
- dump des logs docker en cas d echec

## Email prod avec Brevo (prod uniquement)
Le backend supporte desormais un provider email reel via SMTP (Brevo recommande).

### 1) Configurer la prod sur le VPS
Sur le serveur, dans `~/piano-app`, creez un fichier `.env`:

```bash
cd ~/piano-app
cp .env.example .env
nano .env
```

Valeurs minimales a renseigner:
- `EMAIL_PROVIDER=BREVO`
- `EMAIL_FROM=no-reply@app.piano-academie.com`
- `SMTP_HOST=smtp-relay.brevo.com`
- `SMTP_PORT=587`
- `SMTP_USERNAME=<login SMTP Brevo>`
- `SMTP_PASSWORD=<cle SMTP Brevo>`
- `SMTP_USE_TLS=true`

Puis redeployer:

```bash
docker compose up -d --build
docker compose logs --tail=100 backend
```

### 2) Important DNS domaine
Pour eviter les emails en spam:
- SPF (Brevo)
- DKIM (Brevo)
- DMARC (votre domaine)

### 3) Note de securite
- Le workflow de deploiement n ecrase plus `.env`/`.env.*` sur le VPS.
- Ne jamais commiter les secrets SMTP dans Git.
