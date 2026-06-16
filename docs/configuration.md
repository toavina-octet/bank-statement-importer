# Guide de configuration

Ce guide decrit les parametres requis pour connecter l'application aux boites mail, a Odoo et a un scheduler externe.

## Fichier `.env`

Le fichier `.env` contient les secrets et les parametres runtime.

Exemple:

```bash
LOG_LEVEL=INFO
LOGS_DIR=./logs
LOG_FILE=bank_importer.log
LOG_MAX_BYTES=10485760
LOG_BACKUP_COUNT=5
RUN_MODE=api
API_HOST=0.0.0.0
API_PORT=8080
API_TOKEN=change-this-token
DATABASE_URL=sqlite:///./data/bank_importer.sqlite3
CLIENTS_CONFIG_PATH=./config/clients.yml
VINAMORA_ODOO_PASSWORD=secret
VINAMORA_IMAP_PASSWORD=secret
```

Variables principales:

- `RUN_MODE`: `api` en production (utilisé par un scheduler externe), `once` pour un passage manuel.
- `API_HOST`: interface d'ecoute HTTP. En Docker, garder `0.0.0.0`.
- `API_PORT`: port HTTP expose par le conteneur.
- `API_TOKEN`: token bearer attendu par le scheduler externe ou l'API publique.
- `DATABASE_URL`: base SQLite de suivi et d'historique.
- `LOGS_DIR`: dossier des logs persistants.
- `LOG_MAX_BYTES`: taille maximum du fichier actif avant rotation.
- `LOG_BACKUP_COUNT`: nombre de fichiers de rotation conserves.

## Fichier `config/clients.yml`

Le fichier `config/clients.yml` contient les clients, leurs acces Odoo, leurs boites mail et leurs expediteurs bancaires autorises.

Structure:

```yaml
clients:
  sit_palais:
    odoo:
      version: 14
      url: "https://sit-palais-odoo.example.com"
      database: "sit_palais"
      username: "technical-user@example.com"
      password_env: "SIT_PALAIS_ODOO_PASSWORD"
    mailbox:
      email: "bank-statements@example.com"
      host: "imap.example.com"
      port: 993
      username: "bank-statements@example.com"
      password_env: "SIT_PALAIS_IMAP_PASSWORD"
      folder: "INBOX"
      use_ssl: true
    banking:
      authorized_senders:
        - "releves@example-bank.com"
```

Regles:

- `clients.<slug>` doit etre unique.
- `odoo.version` supporte les versions attendues par le CDC: 14, 17 et 19.
- `odoo.password_env` doit pointer vers une variable presente dans `.env`.
- `mailbox.password_env` doit pointer vers une variable presente dans `.env`.
- `banking.authorized_senders` doit contenir uniquement les adresses banques autorisees.
- Les mots de passe ne doivent pas etre ecrits dans `config/clients.yml`.

## Securite

- Utiliser IMAPS avec `use_ssl: true`.
- Utiliser HTTPS pour Odoo et pour l'endpoint public appele par un scheduler externe.
- Generer un `API_TOKEN` long et aleatoire.
- Restreindre l'acces au reverse proxy si possible, par IP ou WAF.
- Ne jamais commit `.env` ni `config/clients.yml`.

## Endpoint de déclenchement

URL:

```text
POST https://importer.example.com/api/import/run
```

Headers:

```text
Authorization: Bearer <API_TOKEN>
Content-Type: application/json
```

Body pour tous les clients:

```json
{}
```

Body pour un client:

```json
{
  "client_slug": "sit_palais"
}
```
