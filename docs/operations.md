# Guide d'exploitation

Ce guide decrit les operations courantes: lancement, supervision, diagnostic et reprise.

## Lancer le service API

En production (déployé sur un serveur, déclenché par un scheduler externe) :

```bash
docker compose up -d --build
```

Verifier que le conteneur tourne:

```bash
docker compose ps
```

Verifier l'API:

```bash
curl http://127.0.0.1:8080/health
```

## Declencher un import manuellement

Depuis le serveur:

```bash
curl -X POST http://127.0.0.1:8080/api/import/run \
  -H "Authorization: Bearer $API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}'
```

Pour un client specifique:

```bash
curl -X POST http://127.0.0.1:8080/api/import/run \
  -H "Authorization: Bearer $API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"client_slug":"sit_palais"}'
```

## Reponse API attendue

```json
{
  "status": "success",
  "summary": {
    "requested_client_slug": null,
    "processed_clients": 5,
    "imported_documents": 3,
    "duplicate_documents": 1,
    "rejected_messages": 0,
    "client_summaries": []
  }
}
```

## Logs

Les logs sont disponibles:

- Dans Docker: `docker compose logs -f bank-importer`
- Dans les fichiers persistants: `./logs/bank_importer.log`

Rotation:

- `LOG_MAX_BYTES` controle la taille maximum du fichier actif.
- `LOG_BACKUP_COUNT` controle le nombre d'archives conservees.

Les logs tracent:

- Connexions IMAP reussies.
- Connexions IMAP echouees.
- Imports reussis.
- Imports rejetes.
- Doublons detectes.
- Erreurs techniques.

## Base de suivi SQLite

La base par defaut est:

```text
./data/bank_importer.sqlite3
```

Requete de suivi:

```sql
SELECT account_number, new_balance, client_slug, statement_date, is_coherent, created_at
FROM processed_documents
ORDER BY created_at DESC
LIMIT 20;
```

## Reprise et incidents

Doublon detecte:

- Le fichier a deja ete traite selon son hash SHA-256.
- Aucun nouvel archivage Odoo n'est effectue.

Expediteur non autorise:

- Le mail est rejete.
- Ajouter l'adresse dans `banking.authorized_senders` uniquement apres validation metier.

Erreur de coherence:

- Le PDF est extrait mais le solde calcule ne correspond pas au nouveau solde.
- Verifier le format du releve et le parseur bancaire.

Erreur Odoo:

- Verifier l'URL, la base, le compte technique et le mot de passe.
- Verifier que l'instance Odoo est joignable depuis le serveur.

Erreur IMAP:

- Verifier host, port, SSL, username, password et dossier.
- Verifier que la boite mail accepte les connexions IMAPS.

## Commandes utiles

Redemarrer le service:

```bash
docker compose restart bank-importer
```

Arreter le service:

```bash
docker compose down
```

Voir les derniers logs:

```bash
tail -n 100 logs/bank_importer.log
```
