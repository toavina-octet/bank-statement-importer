# Guide de mise en production

Ce guide decrit le deploiement cible.

## Architecture cible

```text
Scheduler (ex: scheduler externe)
  -> HTTPS POST /api/import/run
  -> Reverse proxy public
  -> Application Docker bank-importer
  -> IMAPS banques
  -> Odoo HTTPS
  -> SQLite local
  -> Logs locaux avec rotation
```

Le scheduler (par ex. un service externe) sert uniquement à déclencher l'import périodique. L'application traite les mails, extrait les PDF, contrôle les données et archive dans Odoo.

## Preparation serveur

Installer Docker et Docker Compose.

Creer le dossier applicatif:

```bash
sudo mkdir -p /opt/bank-statement-importer
sudo chown "$USER":"$USER" /opt/bank-statement-importer
```

Installer le projet:

```bash
cd /opt
git clone <repository-url> bank-statement-importer
cd bank-statement-importer
```

Creer les dossiers persistants sur le serveur d'exécution (là où `docker compose` sera lancé) :

```bash
mkdir -p data logs config
```

## Configuration production

Creer et preparer la configuration sur le serveur d'exécution (là où `docker compose` sera lancé) :

```bash
cp .env.template .env
cp config/clients.example.yml config/clients.yml

# Editer .env et renseigner les secrets (ne pas commit)
# Exemples à définir dans .env:
# RUN_MODE=api
# API_HOST=0.0.0.0
# API_PORT=8080
# API_TOKEN=<token-long-aleatoire>
# DATABASE_URL=sqlite:///./data/bank_importer.sqlite3
# CLIENTS_CONFIG_PATH=./config/clients.yml
# SIT_PALAIS_ODOO_PASSWORD=<secret>
# SIT_PALAIS_IMAP_PASSWORD=<secret>
```

Dans `config/clients.yml`, renseigner les clients reels.

## Reverse proxy HTTPS

n'importe quel scheduler doit appeler une URL HTTPS publique. Le reverse proxy doit transferer vers l'application locale.

Exemple Nginx:

```nginx
server {
    listen 443 ssl;
    server_name importer.example.com;

    ssl_certificate /etc/letsencrypt/live/importer.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/importer.example.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
    }
}
```

Recommandations:

- Activer HTTPS uniquement.
- Restreindre l'acces par IP si l'environnement le permet.
- Garder `API_TOKEN` secret.
- Ne pas exposer SQLite ni les dossiers `data/` et `logs/`.

## Demarrage

```bash
docker compose up -d --build
```

Verifier:

```bash
docker compose ps
curl https://importer.example.com/health
```

Declencher un test:

```bash
curl -X POST https://importer.example.com/api/import/run \
  -H "Authorization: Bearer $API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}'
```

## Workflow scheduler

Le workflow detaille est decrit dans `docs/scheduler-workflow.md`.

Resume:

1. `Schedule Trigger`
2. `HTTP Request` vers `POST https://importer.example.com/api/import/run`
3. `IF` sur `{{$json.status}} equals success`
4. Notification sur la branche erreur

## Verification post-deploiement

Verifier les logs:

```bash
docker compose logs --tail=100 bank-importer
tail -n 100 logs/bank_importer.log
```

Verifier SQLite:

```bash
sqlite3 data/bank_importer.sqlite3 \
  "SELECT client_slug, account_number, new_balance, is_coherent, created_at FROM processed_documents ORDER BY created_at DESC LIMIT 10;"
```

Verifier Odoo:

- Aller dans les pieces jointes Odoo.
- Verifier que le PDF est archive.
- Verifier la description: client, compte, date du releve, soldes, coherence, expediteur, UID mail.

## Sauvegardes

A sauvegarder:

- `data/bank_importer.sqlite3`
- `config/clients.yml`
- `.env` dans un coffre securise
- `logs/` selon la politique d'audit

Ne pas exposer ces fichiers publiquement.
