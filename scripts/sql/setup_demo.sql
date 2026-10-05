-- Optional demo subject tables. Do not run against edladmin if live data already exists.
-- Edit dcsa_catalog.dcsa_api if this environment uses another catalog.schema.
-- Point the app with DCSA_CATALOG_SCHEMA=dcsa_catalog.dcsa_api

CREATE SCHEMA IF NOT EXISTS dcsa_catalog.dcsa_api;

CREATE TABLE IF NOT EXISTS dcsa_catalog.dcsa_api.subject_identity (
  SSN STRING,
  FIRST_NAME STRING,
  LAST_NAME STRING,
  DATE_OF_BIRTH STRING,
  PLACE_OF_BIRTH STRING,
  SEX STRING,
  CITIZENSHIP STRING,
  MARITAL_STATUS STRING,
  UPDATED_TS STRING,
  RECORD_VERSION STRING
)
USING DELTA;

CREATE TABLE IF NOT EXISTS dcsa_catalog.dcsa_api.subject_status (
  SSN STRING,
  ORG_CODE STRING,
  POSITION_TITLE STRING,
  DUTY_LOCATION STRING,
  RISK_TIER STRING,
  ELIGIBILITY_LEVEL STRING,
  STATUS_CODE STRING,
  STATUS_EFFECTIVE_DATE STRING,
  UPDATED_TS STRING,
  RECORD_VERSION STRING
)
USING DELTA;

CREATE TABLE IF NOT EXISTS dcsa_catalog.dcsa_api.subject_check (
  CHECK_ID STRING,
  SSN STRING,
  LOCATION_CODE STRING,
  CHECK_TYPE STRING,
  RESULT_CODE STRING,
  RESULT_SCORE STRING,
  CHECKED_TS STRING,
  LOAD_SEQ STRING
)
USING DELTA;

CREATE TABLE IF NOT EXISTS dcsa_catalog.dcsa_api.subject_activity (
  ACTIVITY_ID STRING,
  SSN STRING,
  LOCATION_CODE STRING,
  ACTIVITY_TYPE STRING,
  DETAIL STRING,
  EVENT_TS STRING,
  LOAD_SEQ STRING
)
USING DELTA;

CREATE TABLE IF NOT EXISTS dcsa_catalog.dcsa_api.subject_signal (
  SIGNAL_ID STRING,
  SSN STRING,
  LOCATION_CODE STRING,
  SIGNAL_TYPE STRING,
  SEVERITY STRING,
  SIGNAL_TS STRING,
  LOAD_SEQ STRING
)
USING DELTA;

DELETE FROM dcsa_catalog.dcsa_api.subject_identity WHERE SSN LIKE '99900%';
DELETE FROM dcsa_catalog.dcsa_api.subject_status WHERE SSN LIKE '99900%';
DELETE FROM dcsa_catalog.dcsa_api.subject_check WHERE SSN LIKE '99900%';
DELETE FROM dcsa_catalog.dcsa_api.subject_activity WHERE SSN LIKE '99900%';
DELETE FROM dcsa_catalog.dcsa_api.subject_signal WHERE SSN LIKE '99900%';

INSERT INTO dcsa_catalog.dcsa_api.subject_identity
VALUES
  ('999001111', 'Kevin', 'Jackson', '1969-02-10', 'VA', 'M', 'USA', 'M', '2026-09-01T12:00:00', '1'),
  ('999001112', 'Maria', 'Santos', '1985-03-22', 'TX', 'F', 'USA', 'S', '2026-09-01T12:00:00', '1'),
  ('999001113', 'Maria', 'Santos', '1985-03-22', 'CA', 'F', 'USA', 'M', '2026-09-01T12:00:00', '1'),
  ('999001114', 'Alex', 'Rivera', '1990-07-01', 'MD', 'X', 'USA', 'S', '2026-09-01T12:00:00', '1');

INSERT INTO dcsa_catalog.dcsa_api.subject_status
VALUES
  ('999001111', 'DCSA', 'Analyst', 'Quantico, VA', 'M', 'S', 'ELIGIBLE', '2024-06-01', '2026-09-01T12:00:00', '1'),
  ('999001112', 'DCSA', 'Specialist', 'Dallas, TX', 'L', 'S', 'ELIGIBLE', '2025-01-15', '2026-09-01T12:00:00', '1'),
  ('999001113', 'DCSA', 'Investigator', 'Sacramento, CA', 'M', 'TS', 'ELIGIBLE', '2024-11-20', '2026-09-01T12:00:00', '1'),
  ('999001114', 'DCSA', 'Technician', 'Fort Meade, MD', 'L', 'S', 'PENDING', '2026-02-01', '2026-09-01T12:00:00', '1');

INSERT INTO dcsa_catalog.dcsa_api.subject_check
VALUES
  ('CHK-1001', '999001111', 'QAN', 'NACI', 'FAVORABLE', '0', '2024-05-15T08:00:00', '12'),
  ('CHK-1002', '999001112', 'DAL', 'NACI', 'FAVORABLE', '0', '2025-01-02T09:30:00', '4'),
  ('CHK-1003', '999001113', 'SAC', 'SSBI', 'FAVORABLE', '0', '2024-10-18T11:00:00', '7'),
  ('CHK-1004', '999001114', 'FME', 'NACI', 'PENDING', '0', '2026-01-22T16:15:00', '2');

INSERT INTO dcsa_catalog.dcsa_api.subject_activity
VALUES
  ('ACT-2001', '999001111', 'QAN', 'INVESTIGATION', 'Case opened', '2024-04-02T14:30:00', '8'),
  ('ACT-2002', '999001112', 'DAL', 'REINVESTIGATION', 'Periodic review started', '2024-12-10T10:00:00', '3'),
  ('ACT-2003', '999001113', 'SAC', 'INVESTIGATION', 'Case closed favorable', '2024-10-20T13:45:00', '5'),
  ('ACT-2004', '999001114', 'FME', 'ONBOARDING', 'Package received', '2026-01-08T08:20:00', '1');

INSERT INTO dcsa_catalog.dcsa_api.subject_signal
VALUES
  ('SIG-3001', '999001111', 'QAN', 'CV_ALERT', 'LOW', '2025-11-03T09:12:00', '3'),
  ('SIG-3002', '999001112', 'DAL', 'CV_ALERT', 'LOW', '2025-08-14T15:40:00', '1'),
  ('SIG-3003', '999001113', 'SAC', 'CV_ALERT', 'MEDIUM', '2025-03-09T07:05:00', '2'),
  ('SIG-3004', '999001114', 'FME', 'CV_ALERT', 'LOW', '2026-03-01T12:00:00', '1');
