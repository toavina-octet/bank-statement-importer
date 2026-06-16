# Workflow scheduler

Ce workflow declenche l'application en production. Le scheduler externe ne traite pas les releves: il planifie l'appel HTTP et alerte en cas d'erreur.

## Prerequis

- L'application tourne avec `RUN_MODE=api` et est déployée sur un serveur (via Docker Compose).
- `API_TOKEN` est configuré dans `.env`.
- Le serveur expose l'API en HTTPS, par exemple `https://importer.example.com`.
- Le reverse proxy transfère les requêtes vers `http://127.0.0.1:8080`.

## Nodes

1. `Schedule Trigger`

Configurer la frequence souhaitee, par exemple toutes les 15 minutes.

2. `HTTP Request`

- Method: `POST`
- URL: `https://importer.example.com/api/import/run`
- Authentication: `None`
- Send Headers: `true`
- Header `Authorization`: `Bearer <API_TOKEN>`
- Header `Content-Type`: `application/json`
- Send Body: `true`
- Body Content Type: `JSON`
- Body:

```json
{}
```

Pour executer un seul client:

```json
{
  "client_slug": "sit_palais"
}
```

3. `IF`

Verifier que l'import a reussi:

- Value 1: `{{$json.status}}`
- Operation: `equals`
- Value 2: `success`

4. Notification d'erreur

Sur la branche `false`, ajouter un node de notification (Email, Slack, Teams, etc.)

Message conseille:

```text
Import releves bancaires en erreur.
Status: {{$json.status}}
Error: {{$json.error}}
Message: {{$json.message}}
```

## Reponse attendue

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

## Test manuel

```bash
curl -X POST https://importer.example.com/api/import/run \
  -H "Authorization: Bearer $API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}'
```
