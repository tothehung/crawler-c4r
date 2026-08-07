-- BigQuery DDL for the Solodit findings dataset.
--
-- Replace ${PROJECT_ID} and ${DATASET} before executing, for example:
--   bq query --use_legacy_sql=false "$(Get-Content sql/create_tables.sql -Raw)"

CREATE SCHEMA IF NOT EXISTS `${PROJECT_ID}.${DATASET}`
OPTIONS (
  description = 'Solodit findings crawled by w3goaudit_crawler',
  location = '${LOCATION}'
);

CREATE TABLE IF NOT EXISTS `${PROJECT_ID}.${DATASET}.findings`
(
  id STRING NOT NULL,
  kind STRING,
  auditfirm_id STRING,
  impact STRING,
  finders_count INT64,
  protocol_id STRING,
  title STRING NOT NULL,
  content STRING,
  summary STRING,
  report_date DATE,
  contest_prize_txt STRING,
  contest_link STRING,
  sponsor_name STRING,
  sponsor_link STRING,
  quality_score FLOAT64,
  general_score FLOAT64,
  source_link STRING,
  github_link STRING,
  pdf_link STRING,
  pdf_page_from INT64,
  contest_id STRING,
  slug STRING NOT NULL,
  firm_name STRING,
  firm_logo_square STRING,
  protocol_name STRING,
  bookmarked BOOL,
  read BOOL,
  finder_handles ARRAY<STRING>,
  auditfirm JSON,
  protocol JSON,
  issue_finders JSON,
  issue_tag_scores JSON,
  source_payload JSON,
  source_payload_hash STRING,
  crawled_at TIMESTAMP NOT NULL,
  loaded_at TIMESTAMP NOT NULL
)
PARTITION BY DATE(loaded_at)
CLUSTER BY impact, firm_name, protocol_name, report_date
OPTIONS (
  description = 'Latest Solodit finding records keyed by id.'
);

CREATE TABLE IF NOT EXISTS `${PROJECT_ID}.${DATASET}.findings_staging`
(
  id STRING NOT NULL,
  kind STRING,
  auditfirm_id STRING,
  impact STRING,
  finders_count INT64,
  protocol_id STRING,
  title STRING NOT NULL,
  content STRING,
  summary STRING,
  report_date DATE,
  contest_prize_txt STRING,
  contest_link STRING,
  sponsor_name STRING,
  sponsor_link STRING,
  quality_score FLOAT64,
  general_score FLOAT64,
  source_link STRING,
  github_link STRING,
  pdf_link STRING,
  pdf_page_from INT64,
  contest_id STRING,
  slug STRING NOT NULL,
  firm_name STRING,
  firm_logo_square STRING,
  protocol_name STRING,
  bookmarked BOOL,
  read BOOL,
  finder_handles ARRAY<STRING>,
  auditfirm JSON,
  protocol JSON,
  issue_finders JSON,
  issue_tag_scores JSON,
  source_payload JSON,
  source_payload_hash STRING,
  crawled_at TIMESTAMP NOT NULL,
  loaded_at TIMESTAMP NOT NULL
)
PARTITION BY DATE(loaded_at)
CLUSTER BY impact, firm_name, protocol_name, report_date
OPTIONS (
  description = 'Batch staging table for Solodit findings before MERGE into findings.'
);
