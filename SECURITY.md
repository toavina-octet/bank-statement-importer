# Security Policy

## Donnees sensibles

Ce projet manipule des documents bancaires, des acces e-mail et des acces Odoo. Les elements suivants ne doivent pas etre versionnes:

- fichiers `.env`
- `config/clients.yml`
- PDF bancaires reels
- exports de base de donnees
- logs contenant des donnees personnelles

## Configuration

- Utiliser IMAPS sur le port 993.
- Utiliser HTTPS pour Odoo lorsque disponible.
- Creer un utilisateur technique Odoo avec les droits minimaux necessaires.
- Preferer des mots de passe applicatifs pour les boites e-mail.

## Signalement

En cas de fuite de secret, revoquer immediatement le secret concerne, puis nettoyer l'historique Git si le secret a ete pousse.
