# DCSA API

FastAPI backend for Databricks Apps, deployed with a Declarative Automation Bundle (DAB).

**Workspace:** `https://govfood-dsca.cloud.databricks.us/`

## Layout

```
app/
  models/          # Pydantic request/response schemas
    reports/       # One typed envelope per report (auto-registered as routes)
    report_contract.py  # Shared section-row models + catalog schemas
  services/        # Identity, report assembly, request log, catalog
  routes/          # HTTP endpoints (FPVR routes generated from report models)
  core/            # YAML settings, OBO SQL, jobs
  main.py          # FastAPI app (OpenAPI at /docs)
config.yaml        # Sources, reports, jobs, warehouse (validated at startup)
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

`config.yaml` is the live contract. Invalid YAML fails startup rather than serving a half-configured API. Identifiers are allowlisted; filter values are bound as SQL parameters. YAML cannot express joins, extra predicates, or arbitrary SQL.

The public catalog (`/api/v1/catalog` and `/help`) is generated from the same config plus optional Pydantic row models.

## Adding a source

A **source** is a reusable table or view. Multiple reports can share one source.

1. Add an entry under `sources:` in `config.yaml`. Copy an existing source (for example `identity` or `awards`) and change names.

   ```yaml
   sources:
     training:
       table: subject_training          # table, schema.table, or catalog.schema.table
       # catalog: other_catalog         # optional override of default_catalog_schema
       # schema: other_schema
       filter:
         column: SSN
         parameter: subject_ssn         # only allowed bind parameter today
       columns:
         - SSN
         - COURSE_NAME
         - COMPLETED_DATE
       omit_from_output:
         - SSN                          # never returned in JSON
       fields:                          # optional; omitted public columns are nullable strings
         COURSE_NAME: { type: string, nullable: true }
         COMPLETED_DATE: { type: date, nullable: true }
   ```

2. Every identifier (catalog, schema, table, column, `fields` key) must be `[A-Za-z0-9_]+`. The filter column and any `omit_from_output` names must appear in `columns`. Each `fields` key must be a public column (in `columns`, not in `omit_from_output`).
3. Optional `fields` sets catalog (and generated row-model) types. Allowed `type` values: `string`, `integer`, `number`, `boolean`, `date`, `datetime`. Without `fields`, public columns still work and are documented as nullable strings. Typed OpenAPI envelopes still live under `app/models/reports/`.
4. Optional: add a sample row in `app/services/catalog.py` (`_SAMPLE_ROWS`) so `/help` examples look realistic.

`awards` in `config.yaml` is a complete example of a source that lives in a non-default schema (`ryan_mock.usa_spending_mock_awards`).

## Adding a report

A **report** is a named payload: sections (each pointing at a source), a readiness rule, and optional job kickoff.

1. Add the report under `reports:` in `config.yaml`. The YAML key (`FPVR-8`, `Awards`, …) is normalized at load time to lowercase with hyphens removed (`fpvr8`, `awards`). That normalized code is the HTTP path segment and must match the Python module name in step 3.

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

2. Choose a **readiness** mode:

   | Mode | Extra fields | Ready when |
   | --- | --- | --- |
   | `always` | — | Immediately after assemble |
   | `section_non_empty` | `section` | That section has at least one row |
   | `any_section_non_empty` | `sections` | Any listed section has rows |
   | `all_sections_non_empty` | `sections` | Every listed section has at least one row |
   | `field_present` | `section`, `field` | Any row in that section has a non-empty field (field must be selected and not omitted) |

   If the report is pending and `on_pending.job` is set, the app starts that Databricks job once (idempotent on `request_id`) with allowlisted placeholders such as `{{request_id}}` and `{{subject_ssn}}`. Define the job under `jobs:` first. Callers poll GET until readiness passes.

3. Add typed OpenAPI models so FastAPI can register the routes. Create `app/models/reports/{normalized_code}.py`. The file stem must be the normalized code (`fpvr8.py`, `awards.py`). Export `{STEM.upper()}RequestAccepted` (for `fpvr8` that is `FPVR8RequestAccepted`).

   Follow `app/models/reports/fpvr6.py` or `app/models/reports/awards.py`:

   - A `*ReportData` model whose fields are the **section names** from YAML, each `list[YourSectionRow]`.
   - A `*Report` subclass of `OfficialReport[YourReportData]`.
   - A `*RequestAccepted` subclass of `OfficialRequestAccepted[YourReport]`.

   Routes are discovered at import time by ``app/models/reports/registry.py`` from that directory. You do not add a new router by hand. After restart, you get:

   - `POST /api/v1/requests/{normalized_code}`
   - `GET /api/v1/requests/{normalized_code}/{request_id}`

4. Restart the app (settings are cached). Confirm the report appears in `/docs`, `/api/v1/catalog`, and `/help`. Invalid config fails at startup with a validation error.

There is a commented template at the bottom of `config.yaml` with the same shape.

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

Table and warehouse names live in `config.yaml` (`databricks.default_catalog_schema`, `databricks.request_log_table`, and each `sources.*.table`). Per-source `catalog` / `schema` override the default. Names may be `table`, `schema.table`, or `catalog.schema.table` (views included).

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

