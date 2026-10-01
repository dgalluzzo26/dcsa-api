# DCSA API

FastAPI backend for Databricks Apps, deployed with a Declarative Automation Bundle (DAB).

**Workspace:** `https://govfood-dsca.cloud.databricks.us/`

## Layout

```
app/
  models/     # Pydantic request/response schemas
  services/   # Business logic / store adapters
  routes/     # HTTP endpoints
  core/       # Settings + Databricks client helpers
  main.py     # FastAPI app (OpenAPI at /docs)
app.yaml      # Databricks Apps process command
databricks.yml
resources/dcsa_api.app.yml
```

## Local run

```bash
cd /Users/david.galluzzo/FBR/dcsa-api
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Open:

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- OpenAPI JSON: http://localhost:8000/openapi.json

## Auth to GovCloud workspace (required before deploy)

No local CLI profile exists yet for this host. Create one:

```bash
databricks auth login \
  --host https://govfood-dsca.cloud.databricks.us \
  --profile govfood-dsca
```

Confirm:

```bash
databricks auth profiles
databricks current-user me --profile govfood-dsca
```

## Deploy (DAB)

```bash
databricks bundle validate -t dev --profile govfood-dsca
databricks bundle deploy -t dev --profile govfood-dsca --auto-approve
databricks apps deploy dcsa-api --profile govfood-dsca --auto-approve
```

After deploy, open the app URL and hit `/docs` to exercise the API.
