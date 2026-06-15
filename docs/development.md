# Environnement de developpement

## A installer

- Python 3.12 ou plus recent
- Docker Desktop
- Git
- VS Code ou PyCharm
- Tesseract OCR, utile pour tester hors Docker

Extensions VS Code recommandees:

- Python
- Ruff
- Docker
- YAML
- GitLens

Verifications:

```powershell
python --version
pip --version
git --version
docker --version
docker compose version
```

## Configuration locale

```powershell
Copy-Item .env.template .env
Copy-Item config/clients.example.yml config/clients.yml
```

Remplir ensuite:

- les parametres IMAPS dans `config/clients.yml`
- les mots de passe IMAPS references par `password_env` dans `.env`
- les acces Odoo dans `.env`
- les clients, versions Odoo et expediteurs autorises dans `config/clients.yml`

Ne jamais commit `.env`, `config/clients.yml`, `data/` ou `logs/`.

## Lancement avec Docker

```powershell
docker compose build
docker compose up
```

Verification ponctuelle:

```powershell
docker compose run --rm bank-importer python -c "import pdfplumber, pytesseract, odoorpc, sqlalchemy; print('ok')"
```

## Ordre de realisation

1. Initialiser la configuration multi-clients.
2. Ajouter la connexion IMAPS et la lecture des messages non traites.
3. Filtrer les expediteurs autorises.
4. Telecharger uniquement les pieces jointes PDF.
5. Calculer un hash SHA-256 et bloquer les doublons.
6. Extraire le texte du PDF avec `pdfplumber`.
7. Basculer sur OCR avec `pytesseract` si le PDF ne contient pas de texte exploitable.
8. Parser les soldes et mouvements bancaires.
9. Controler la coherence: ancien solde + credits - debits = nouveau solde.
10. Archiver le PDF et les metadonnees dans Odoo.
11. Mettre a jour le solde si les donnees sont coherentes.
12. Marquer l'e-mail comme traite.
13. Journaliser les succes, rejets, doublons et erreurs.
