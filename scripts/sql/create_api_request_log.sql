-- Official FPVR request log (App SP writes, callers do not).
-- Run in a Databricks SQL editor. Edit catalog/schema below if this environment
-- uses different names, then set DCSA_REQUEST_LOG_TABLE to the same table.

CREATE SCHEMA IF NOT EXISTS dcsa_catalog.dcsa_api;

CREATE TABLE IF NOT EXISTS dcsa_catalog.dcsa_api.api_request_log (
  request_id STRING,
  report_code STRING,
  subject_ssn STRING,
  first_name STRING,
  last_name STRING,
  date_of_birth STRING,
  status STRING,
  requested_by STRING,
  requested_at STRING,
  ready_at STRING,
  resolution_method STRING
)
USING DELTA;

-- Grant the Databricks App service principal (replace the UUID):
-- GRANT USE SCHEMA ON SCHEMA dcsa_catalog.dcsa_api TO `48789308-d387-46bc-bab4-9c4521f884da`;
-- GRANT SELECT, MODIFY ON TABLE dcsa_catalog.dcsa_api.api_request_log TO `48789308-d387-46bc-bab4-9c4521f884da`;
