# Bank Statement Importer

Application Python conteneurisée pour récupérer automatiquement des relevés bancaires PDF depuis une boîte e-mail IMAPS, contrôler leur validité, extraire les données et les archiver dans Odoo.

## 🚀 Fonctionnalités Implémentées

- **Collecte Multi-Clients** : Connexion IMAPS et récupération des PDF.
- **Validation des Expéditeurs** : Seuls les e-mails provenant de banques autorisées sont traités.
- **Détection de Doublons** : Empreinte SHA-256 pour éviter les imports multiples.
- **Extraction PDF & OCR** : Extraction via `pdfplumber` avec fallback `pytesseract` pour les scans.
- **Contrôle de Cohérente** : Vérification mathématique `Solde Initial + Mouvements = Solde Final`.
- **Archivage Odoo** : Envoi automatique du PDF et des informations traitées vers `ir.attachment` via OdooRPC.
- **Intégration n8n Cloud** : n8n sert de scheduler et déclenche l'API d'import périodiquement.

## 🛠 Architecture & Dépendances

- **Python 3.12+**
- **Bibliothèques** : `pdfplumber`, `pytesseract`, `odoorpc`, `sqlalchemy`.
- **Système** : Tesseract OCR, Poppler (inclus dans le Dockerfile).

## 📚 Documentation CDC

- [Guide d'installation](docs/installation.md)
- [Guide de configuration](docs/configuration.md)
- [Guide d'exploitation](docs/operations.md)
- [Guide de mise en production](docs/production.md)
- [Workflow n8n Cloud](docs/n8n-cloud-workflow.md)

## ⚙️ Configuration

### 1. Variables d'environnement (`.env`)
Copiez `.env.template` vers `.env` et remplissez les informations :
- `DATABASE_URL` : Chemin vers la base SQLite (ex: `sqlite:///./data/bank_importer.sqlite3`).
- `LOGS_DIR`, `LOG_FILE`, `LOG_MAX_BYTES`, `LOG_BACKUP_COUNT` : Fichier de logs et rotation.
- `RUN_MODE` : `api` pour exposer un endpoint déclenché par n8n Cloud, `once` pour un passage manuel.
- `POLL_INTERVAL_SECONDS` : délai entre deux recherches de nouveaux messages uniquement en mode `poll`.
- `API_HOST`, `API_PORT`, `API_TOKEN` : interface HTTP et token bearer pour n8n Cloud.
- `[CLIENT]_ODOO_PASSWORD`, `[CLIENT]_IMAP_PASSWORD` : mots de passe référencés dans le YAML.

### 2. Configuration Clients (`config/clients.yml`)
Définissez vos clients et leurs règles bancaires :
```yaml
clients:
  vinamora:
    odoo:
      version: 19
      url: https://vinamora.odoo.com
      database: vinamora-prod
      username: admin
      password_env: VINAMORA_ODOO_PASSWORD
    mailbox:
      email: bank-statements@example.com
      host: imap.example.com
      port: 993
      username: bank-statements@example.com
      password_env: VINAMORA_IMAP_PASSWORD
      folder: INBOX
      use_ssl: true
    banking:
      authorized_senders:
        - info@banque-exemple.com
```

## 📦 Déploiement

### Sur Linux (Docker Compose)
1. Clonez le dépôt.
2. Préparez `.env` et `config/clients.yml`.
3. Lancez le service :
   ```bash
   docker compose up -d --build
   ```

### Sur Windows (PowerShell)
1. Installez Docker Desktop.
2. Dans le dossier du projet :
   ```powershell
   docker compose up -d --build
   ```

## 🔗 Intégration n8n Cloud (Conformité CDC)

En production, le service fonctionne avec `RUN_MODE=api`; n8n Cloud est responsable du déclenchement périodique via HTTP.
1. **Étape 1** : n8n Cloud appelle `POST https://importer.example.com/api/import/run`.
2. **Étapes 2-8** : Le script Python gère le mail, le PDF, les doublons et la cohérence.
3. **Étape 9** : Le script persiste les informations traitées en SQLite (`/app/data/bank_importer.sqlite3`) pour l'historique et le suivi.
4. **Étape 10** : Le script archive le PDF dans Odoo avec les informations traitées : client, compte, date, soldes, cohérence, expéditeur, UID e-mail et date de réception.
5. **Étape 11** : n8n peut lire SQLite pour supervision, reporting ou relance, mais ne traite pas le relevé bancaire.

Endpoint de déclenchement:
```bash
curl -X POST https://importer.example.com/api/import/run \
  -H "Authorization: Bearer $API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}'
```

Pour limiter le run a un seul client:
```bash
curl -X POST https://importer.example.com/api/import/run \
  -H "Authorization: Bearer $API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"client_slug":"sit_palais"}'
```

### Requête SQL de suivi pour n8n :
```sql
SELECT account_number, new_balance, client_slug, statement_date 
FROM processed_documents 
WHERE is_coherent = 1 
ORDER BY created_at DESC 
LIMIT 10;
```

## 🧪 Tests et Validation

```powershell
# Exécuter tous les tests
.\.venv\Scripts\python.exe -m pytest

# Vérifier le linting
.\.venv\Scripts\python.exe -m ruff check .
```

## 📜 Journalisation (Audit)
Les logs sont disponibles dans le dossier `./logs` ou via `docker logs bank-importer`. Par défaut, le fichier actif est `./logs/bank_importer.log`; il est rotaté automatiquement selon `LOG_MAX_BYTES` et `LOG_BACKUP_COUNT`. Ils tracent :
- Succès de connexion et d'import.
- Rejets pour incohérence ou expéditeur non autorisé.
- Détection de doublons.
