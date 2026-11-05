# DCSA API

FastAPI backend for Databricks Apps, deployed with a Declarative Automation Bundle (DAB).

**Workspace:** `https://govfood-dsca.cloud.databricks.us/`

## Layout

```
app/
  models/          # Pydantic request/response schemas
    reports/       # Report envelope factory (OpenAPI models from config.yaml)
    sources/       # Source row factory (OpenAPI models from Unity Catalog + mapping.yml)
    report_contract.py  # Catalog schemas
  services/        # Identity, report assembly, request log, catalog
  routes/          # HTTP endpoints (FPVR routes generated from report models)
  core/            # YAML settings, OBO SQL, jobs
  main.py          # FastAPI app (OpenAPI at /docs)
config.yaml        # Sources (table + filter), reports, jobs, warehouse
mapping.yml        # Optional overlay: rename, omit, or override type/nullability
app.yaml           # Databricks Apps process command
databricks.yml
resources/dcsa_api.app.yml
```

## How reports work

Callers open an official request for one report, then poll until it is ready.

1. **POST** `/api/v1/requests/{report}` with identity (`ssn`, and/or `first_name` + `last_name` + `date_of_birth`, or a `candidate_id` from a prior 409).
2. The service resolves a unique subject via OBO SQL against the required `identity` source (SSN is a join key only; it is never returned).
3. `ReportAssembler` runs one parameterized `SELECT` per report section against the Unity Catalog table or view named in `config.yaml`.
4. YAML **readiness** decides `ready` vs `pending`. Pending reports may start a Databricks job (`on_pending`) and later flip to ready on **GET**.
5. The request log is written as the app service principal; subject and report reads run on-behalf-of the caller (ABAC/RBAC apply).

`config.yaml` is the SQL/catalog contract (tables, filters, reports, jobs). Source **columns and types** are discovered from Unity Catalog at startup. `mapping.yml` is an optional overlay: rename a lake column, hide it (`omit: true`), or override type/nullability. Unmapped columns are public under their lake names. Invalid YAML or a failed schema lookup fails startup rather than serving a half-configured API. Identifiers are allowlisted; filter values are bound as SQL parameters. YAML cannot express joins, extra predicates, or arbitrary SQL.

The public catalog (`/api/v1/catalog` and `/help`) is generated from config, Unity Catalog, mapping overlays, and the generated row models.

Startup requires Databricks credentials (`DATABRICKS_CLIENT_ID`/`DATABRICKS_CLIENT_SECRET` on Apps, or `DATABRICKS_TOKEN` locally) so the app can describe each source table.

## Adding a source

A **source** is a reusable table or view. Multiple reports can share one source. Row models are generated at startup from the Unity Catalog table schema; you do not write a Python class.

1. Add an entry under `sources:` in `config.yaml`. Copy an existing source (for example `identity`) and change names.

   ```yaml
   sources:
     training:
       table: subject_training          # table, schema.table, or catalog.schema.table
       # catalog: other_catalog         # optional override of default_catalog_schema
       # schema: other_schema
       filter:
         column: SSN
         parameter: subject_ssn         # only allowed bind parameter today
   ```

   The app describes that table at startup and offers every column (with Databricks types) on the API.

2. Optionally overlay names and visibility under `sources:` in `mapping.yml`. Unmapped columns keep their lake names. Set `omit: true` for join keys that must not appear in report JSON. You can also override `type` and `nullable`. If `column` is omitted, the YAML key is the lake column name.

   ```yaml
   sources:
     training:
       ssn: { column: SSN, omit: true }
       course_name: { column: COURSE_NAME }
       completed_date: { column: COMPLETED_DATE, type: date }
   ```

3. Every identifier (catalog, schema, table, column, API field) must be `[A-Za-z0-9_]+`. The filter column must exist on the Unity Catalog table. Mapping entries must name real lake columns. `field_present` readiness uses the **API** field name (mapped name, or the lake name if unmapped). Allowed overlay `type` values: `string`, `integer`, `number`, `boolean`, `date`, `datetime`.
4. Optional: add a sample row in `app/services/catalog.py` (`_SAMPLE_ROWS`) so `/help` examples look realistic. Use API field names, not lake columns. Unknown fields in examples are `null`.

## Adding a report

A **report** is a named payload: sections (each pointing at a source), a readiness rule, and optional job kickoff.

1. Add the report under `reports:` in `config.yaml`. The YAML key (`FPVR-8`, `Awards`, …) is the public report code. It is used exactly as written in the HTTP path and logs; no normalization is applied.

   ```yaml
   reports:
     FPVR-8:
       name: Training History
       sections:
         training:
           source: training            # must exist under sources:
         identity:
           source: identity
       readiness:
         mode: section_non_empty
         section: training
       # on_pending:
       #   job: mock_async_job         # optional; key under jobs:
   ```

   Jobs are defined under `jobs:` and referenced by name. Parameter values are literals or quoted placeholders: `{{request_id}}`, `{{report_code}}`, `{{subject_ssn}}`, `{{subject_first_name}}`, `{{subject_last_name}}`, `{{subject_date_of_birth}}`.

   ```yaml
   jobs:
     mock_async_job:
       job_id: 141195585457411
       parameters:
         request_id: "{{request_id}}"
         subject_ssn: "{{subject_ssn}}"
   ```

2. Choose a **readiness** mode:

   | Mode | Extra fields | Ready when |
   | --- | --- | --- |
   | `always` | — | Immediately after assemble |
   | `section_non_empty` | `section` | That section has at least one row |
   | `any_section_non_empty` | `sections` | Any listed section has rows |
   | `all_sections_non_empty` | `sections` | Every listed section has at least one row |
   | `field_present` | `section`, `field` | Any row in that section has a non-empty API field (name from `mapping.yml`, not omitted) |

   If the report is pending and `on_pending.job` is set, the app starts that Databricks job once (idempotent on `request_id`) with allowlisted placeholders such as `{{request_id}}` and `{{subject_ssn}}`. Define the job under `jobs:` first. Callers poll GET until readiness passes.

3. If every section `source` already exists, no Python file is required. OpenAPI envelopes are built at startup from YAML sections and generated source row models. A new source needs a `config.yaml` table + filter (see [Adding a source](#adding-a-source)); its row model is created from Unity Catalog. Startup fails if a section source has no discovered schema.

   Routes are registered from config by ``app/models/reports/registry.py``. After restart, you get:

   - `POST /api/v1/requests/{report_code}` (for example `/api/v1/requests/FPVR-8`)
   - `GET /api/v1/requests/{report_code}/{request_id}`

   The POST body is identity only (`ssn`, `first_name` / `last_name` / `date_of_birth`, or `candidate_id`). Report code is the path.

4. Restart the app (settings and Unity Catalog schemas are cached). Confirm the report appears in `/docs`, `/api/v1/catalog`, and `/help`. Invalid config or a failed table describe fails at startup with a validation error.

## Local run

Set `DATABRICKS_TOKEN` (and optionally `DATABRICKS_HOST` / `DATABRICKS_WAREHOUSE_ID`) so startup can describe Unity Catalog tables.

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

Table and warehouse names live in `config.yaml` (`databricks.default_catalog_schema`, `databricks.request_log_table`, and each `sources.*.table`). Per-source `catalog` / `schema` override the default. Names may be `table`, `schema.table`, or `catalog.schema.table` (views included). Column lists are not in YAML; they come from Unity Catalog.

`DATABRICKS_HOST` and `DATABRICKS_WAREHOUSE_ID` override the YAML host and warehouse when set (Databricks Apps injects both).

## Demo tables

SQL you can run in a Databricks SQL editor (edit catalog/schema names first):

- Request log only: `scripts/sql/create_api_request_log.sql`
- Optional dummy subjects: `scripts/sql/setup_demo.sql`

There is also a CLI wrapper, `scripts/setup_demo.py`, if you want the same demo seed from a terminal. Do not run either against `edladmin` when live data already exists.

Then point `databricks.default_catalog_schema` in `config.yaml` at `dcsa_catalog.dcsa_api` only if the API should read those demo objects.

Seeded people:

- Kevin Jackson (1969-02-10) — unique match, row in every section table
- Two Maria Santos (1985-03-22) — ambiguous name + DOB, row in every section table
- Alex Rivera (1990-07-01) — unique match, row in every section table
- Nora Vale (1971-04-18) — unique match, **identity only** (no status/check/activity/signal). Used by Postman pending cases. Seed into the live API schema with `scripts/sql/seed_pending_identity.sql`.

