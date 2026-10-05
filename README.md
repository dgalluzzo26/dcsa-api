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

## FPVR source config

Reports read whatever tables or views you name. Change the catalog/schema once, or override a single object:

```
DCSA_CATALOG_SCHEMA=dcsa_catalog.edladmin
DCSA_TABLE_IDENTITY=subject_identity
DCSA_TABLE_STATUS=subject_status
DCSA_TABLE_CHECK=subject_check
DCSA_TABLE_ACTIVITY=subject_activity
DCSA_TABLE_SIGNAL=subject_signal
DCSA_REQUEST_LOG_TABLE=dcsa_catalog.dcsa_api.api_request_log
```

Names may be `table`, `schema.table`, or `catalog.schema.table` (views included).
`DCSA_SUBJECT_IDENTITY_TABLE` still wins when it is a three-part name.

## Demo tables

SQL you can run in a Databricks SQL editor (edit catalog/schema names first):

- Request log only: `scripts/sql/create_api_request_log.sql`
- Optional dummy subjects: `scripts/sql/setup_demo.sql`

There is also a CLI wrapper, `scripts/setup_demo.py`, if you want the same demo seed from a terminal. Do not run either against `edladmin` when live data already exists.

Then set `DCSA_CATALOG_SCHEMA=dcsa_catalog.dcsa_api` only if the API should read those demo objects.

Seeded people:

- Kevin Jackson (1969-02-10) — unique match, row in every section table
- Two Maria Santos (1985-03-22) — ambiguous name + DOB, row in every section table
- Alex Rivera (1990-07-01) — unique match, row in every section table

