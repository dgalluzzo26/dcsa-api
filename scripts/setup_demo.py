#!/usr/bin/env python3
"""Create demo FPVR tables and seed a few dummy subjects.

Requires the Databricks CLI and an explicit ``--profile``. Default location is
``dcsa_catalog.dcsa_api`` so live ``edladmin`` streaming tables are left alone.

Point the app at the demo objects with::

    DCSA_CATALOG_SCHEMA=dcsa_catalog.dcsa_api

Example::

    python3 scripts/setup_demo.py --profile govfood-dsca
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys

_SCHEMA = re.compile(r"^[A-Za-z0-9_]+\.[A-Za-z0-9_]+$")
_IDENT = re.compile(r"^[A-Za-z0-9_]+$")
_SP = re.compile(r"^[A-Za-z0-9._@-]+$")


def _statements(schema: str) -> list[str]:
    """Return ordered SQL to create and seed demo objects.

    Args:
        schema: ``catalog.schema`` for demo tables.

    Returns:
        SQL statements in dependency order.
    """
    ident = f"{schema}.subject_identity"
    status = f"{schema}.subject_status"
    check = f"{schema}.subject_check"
    activity = f"{schema}.subject_activity"
    signal = f"{schema}.subject_signal"
    log = f"{schema}.api_request_log"
    return [
        f"CREATE SCHEMA IF NOT EXISTS {schema}",
        f"""
CREATE TABLE IF NOT EXISTS {ident} (
  SSN STRING, FIRST_NAME STRING, LAST_NAME STRING, DATE_OF_BIRTH STRING,
  PLACE_OF_BIRTH STRING, SEX STRING, CITIZENSHIP STRING, MARITAL_STATUS STRING,
  UPDATED_TS STRING, RECORD_VERSION STRING
) USING DELTA
""",
        f"""
CREATE TABLE IF NOT EXISTS {status} (
  SSN STRING, ORG_CODE STRING, POSITION_TITLE STRING, DUTY_LOCATION STRING,
  RISK_TIER STRING, ELIGIBILITY_LEVEL STRING, STATUS_CODE STRING,
  STATUS_EFFECTIVE_DATE STRING, UPDATED_TS STRING, RECORD_VERSION STRING
) USING DELTA
""",
        f"""
CREATE TABLE IF NOT EXISTS {check} (
  CHECK_ID STRING, SSN STRING, LOCATION_CODE STRING, CHECK_TYPE STRING,
  RESULT_CODE STRING, RESULT_SCORE STRING, CHECKED_TS STRING, LOAD_SEQ STRING
) USING DELTA
""",
        f"""
CREATE TABLE IF NOT EXISTS {activity} (
  ACTIVITY_ID STRING, SSN STRING, LOCATION_CODE STRING, ACTIVITY_TYPE STRING,
  DETAIL STRING, EVENT_TS STRING, LOAD_SEQ STRING
) USING DELTA
""",
        f"""
CREATE TABLE IF NOT EXISTS {signal} (
  SIGNAL_ID STRING, SSN STRING, LOCATION_CODE STRING, SIGNAL_TYPE STRING,
  SEVERITY STRING, SIGNAL_TS STRING, LOAD_SEQ STRING
) USING DELTA
""",
        f"""
CREATE TABLE IF NOT EXISTS {log} (
  request_id STRING, report_code STRING, subject_ssn STRING, first_name STRING,
  last_name STRING, date_of_birth STRING, status STRING, requested_by STRING,
  requested_at STRING, ready_at STRING, resolution_method STRING
) USING DELTA
""",
        f"DELETE FROM {ident} WHERE SSN LIKE '99900%'",
        f"DELETE FROM {status} WHERE SSN LIKE '99900%'",
        f"DELETE FROM {check} WHERE SSN LIKE '99900%'",
        f"DELETE FROM {activity} WHERE SSN LIKE '99900%'",
        f"DELETE FROM {signal} WHERE SSN LIKE '99900%'",
        f"""
INSERT INTO {ident}
VALUES
  ('999001111', 'Kevin', 'Jackson', '1969-02-10', 'VA', 'M', 'USA', 'M',
   '2026-09-01T12:00:00', '1'),
  ('999001112', 'Maria', 'Santos', '1985-03-22', 'TX', 'F', 'USA', 'S',
   '2026-09-01T12:00:00', '1'),
  ('999001113', 'Maria', 'Santos', '1985-03-22', 'CA', 'F', 'USA', 'M',
   '2026-09-01T12:00:00', '1'),
  ('999001114', 'Alex', 'Rivera', '1990-07-01', 'MD', 'X', 'USA', 'S',
   '2026-09-01T12:00:00', '1')
""",
        f"""
INSERT INTO {status}
VALUES
  ('999001111', 'DCSA', 'Analyst', 'Quantico, VA', 'M', 'S', 'ELIGIBLE',
   '2024-06-01', '2026-09-01T12:00:00', '1'),
  ('999001112', 'DCSA', 'Specialist', 'Dallas, TX', 'L', 'S', 'ELIGIBLE',
   '2025-01-15', '2026-09-01T12:00:00', '1'),
  ('999001113', 'DCSA', 'Investigator', 'Sacramento, CA', 'M', 'TS', 'ELIGIBLE',
   '2024-11-20', '2026-09-01T12:00:00', '1'),
  ('999001114', 'DCSA', 'Technician', 'Fort Meade, MD', 'L', 'S', 'PENDING',
   '2026-02-01', '2026-09-01T12:00:00', '1')
""",
        f"""
INSERT INTO {check}
VALUES
  ('CHK-1001', '999001111', 'QAN', 'NACI', 'FAVORABLE', '0',
   '2024-05-15T08:00:00', '12'),
  ('CHK-1002', '999001112', 'DAL', 'NACI', 'FAVORABLE', '0',
   '2025-01-02T09:30:00', '4'),
  ('CHK-1003', '999001113', 'SAC', 'SSBI', 'FAVORABLE', '0',
   '2024-10-18T11:00:00', '7'),
  ('CHK-1004', '999001114', 'FME', 'NACI', 'PENDING', '0',
   '2026-01-22T16:15:00', '2')
""",
        f"""
INSERT INTO {activity}
VALUES
  ('ACT-2001', '999001111', 'QAN', 'INVESTIGATION', 'Case opened',
   '2024-04-02T14:30:00', '8'),
  ('ACT-2002', '999001112', 'DAL', 'REINVESTIGATION', 'Periodic review started',
   '2024-12-10T10:00:00', '3'),
  ('ACT-2003', '999001113', 'SAC', 'INVESTIGATION', 'Case closed favorable',
   '2024-10-20T13:45:00', '5'),
  ('ACT-2004', '999001114', 'FME', 'ONBOARDING', 'Package received',
   '2026-01-08T08:20:00', '1')
""",
        f"""
INSERT INTO {signal}
VALUES
  ('SIG-3001', '999001111', 'QAN', 'CV_ALERT', 'LOW',
   '2025-11-03T09:12:00', '3'),
  ('SIG-3002', '999001112', 'DAL', 'CV_ALERT', 'LOW',
   '2025-08-14T15:40:00', '1'),
  ('SIG-3003', '999001113', 'SAC', 'CV_ALERT', 'MEDIUM',
   '2025-03-09T07:05:00', '2'),
  ('SIG-3004', '999001114', 'FME', 'CV_ALERT', 'LOW',
   '2026-03-01T12:00:00', '1')
""",
    ]


def _grant_statements(schema: str, principal: str) -> list[str]:
    """Return grants so a caller or app SP can use the demo schema.

    Args:
        schema: ``catalog.schema``.
        principal: Unity Catalog principal name.

    Returns:
        GRANT statements.
    """
    quoted = f"`{principal}`"
    tables = (
        "subject_identity",
        "subject_status",
        "subject_check",
        "subject_activity",
        "subject_signal",
        "api_request_log",
    )
    stmts = [
        f"GRANT USE SCHEMA ON SCHEMA {schema} TO {quoted}",
        f"GRANT MODIFY ON TABLE {schema}.api_request_log TO {quoted}",
    ]
    stmts.extend(f"GRANT SELECT ON TABLE {schema}.{table} TO {quoted}" for table in tables)
    return stmts


def _run_sql(sql: str, *, profile: str, warehouse: str) -> None:
    """Execute one SQL statement with the Databricks CLI.

    Args:
        sql: Statement text.
        profile: CLI profile name.
        warehouse: SQL warehouse id.

    Raises:
        SystemExit: If the CLI returns a non-zero status or a failed statement.
    """
    cmd = [
        "databricks",
        "experimental",
        "aitools",
        "tools",
        "query",
        "--warehouse",
        warehouse,
        "--profile",
        profile,
        "--output",
        "json",
        sql,
    ]
    result = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        sys.stderr.write(result.stderr or result.stdout)
        raise SystemExit(result.returncode)
    payload = json.loads(result.stdout) if result.stdout.strip().startswith("{") else None
    if isinstance(payload, dict) and payload.get("state") == "FAILED":
        error = (payload.get("error") or {}).get("message") or result.stdout
        raise SystemExit(error)
    if isinstance(payload, list):
        for item in payload:
            if item.get("state") == "FAILED":
                error = (item.get("error") or {}).get("message") or str(item)
                raise SystemExit(error)


def main() -> None:
    """Parse CLI arguments and install demo tables."""
    parser = argparse.ArgumentParser(description="Create DCSA FPVR demo tables and dummy rows.")
    parser.add_argument(
        "--profile",
        required=True,
        help="Databricks CLI profile (never inferred).",
    )
    parser.add_argument(
        "--warehouse",
        default="c56ad4dc84dcac90",
        help="SQL warehouse id.",
    )
    parser.add_argument(
        "--catalog-schema",
        default="dcsa_catalog.dcsa_api",
        help="Unity Catalog catalog.schema for demo tables.",
    )
    parser.add_argument(
        "--grant-to",
        default="",
        help="Optional principal to GRANT SELECT (and MODIFY on the request log).",
    )
    args = parser.parse_args()
    if not _SCHEMA.match(args.catalog_schema):
        raise SystemExit(f"Invalid --catalog-schema: {args.catalog_schema!r}")
    if not re.match(r"^[A-Za-z0-9._-]+$", args.profile):
        raise SystemExit(f"Invalid --profile: {args.profile!r}")
    statements = _statements(args.catalog_schema)
    if args.grant_to:
        if not _SP.match(args.grant_to):
            raise SystemExit(f"Invalid --grant-to: {args.grant_to!r}")
        statements.extend(_grant_statements(args.catalog_schema, args.grant_to))
    for sql in statements:
        compact = " ".join(sql.split())
        print(compact[:120] + ("…" if len(compact) > 120 else ""))
        _run_sql(sql, profile=args.profile, warehouse=args.warehouse)
    print(f"Demo tables ready in {args.catalog_schema}")
    print("Point the app with DCSA_CATALOG_SCHEMA=" + args.catalog_schema)


if __name__ == "__main__":
    main()
