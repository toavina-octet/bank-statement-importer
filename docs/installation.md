# Guide d'installation

Ce guide decrit l'installation de l'application d'import automatique des releves bancaires.

## Prerequis

- Serveur Linux recommande pour la production.
- Docker et Docker Compose.
- Acces reseau sortant vers les serveurs IMAPS des boites mail.
- Acces reseau sortant vers les instances Odoo en HTTPS.
- Un domaine HTTPS public si n8n Cloud doit declencher l'application.
- Comptes techniques Odoo pour chaque client.
- Identifiants IMAPS pour chaque boite mail surveillee.

Verification:

```bash
docker --version
docker compose version
git --version
```

## Recuperer le projet

```bash
git clone <repository-url> bank-statement-importer
cd bank-statement-importer
```

Si le projet est deja present sur le serveur:

```bash
cd /opt/bank-statement-importer
git pull
```

## Creer les fichiers de configuration

```bash
cp .env.template .env
cp config/clients.example.yml config/clients.yml
```

Les fichiers suivants ne doivent pas etre commit:

- `.env`
- `config/clients.yml`
- `data/`
- `logs/`

## Construire l'image Docker

```bash
docker compose build
```

## Verifier les dependances runtime

```bash
docker compose run --rm bank-importer python -c "import pdfplumber, pytesseract, odoorpc, sqlalchemy; print('ok')"
```

La commande doit afficher `ok`.

## Lancement local de validation

Pour lancer un passage unique sans API:

```bash
RUN_MODE=once docker compose run --rm bank-importer
```

Pour lancer le service API utilise par n8n Cloud:

```bash
docker compose up -d --build
```

Verification:

```bash
curl http://127.0.0.1:8080/health
```

Reponse attendue:

```json
{
  "status": "ok"
}
```
