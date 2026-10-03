# BigQuery Schema

## Knowledge extension v1 (opt-in)

Phase 1 adds a separate [data contract](knowledge-data-contract-v1.md) and
[additive migration](../sql/migrations/001_knowledge_contract_v1.sql) for six new
tables. The migration does not change the three legacy tables below and is not
executed by existing crawler commands. See the contract for logical keys,
relationships, JSON serialization, validation and rollout requirements.

## Existing crawler tables

The crawler writes Solodit findings and sync state into three BigQuery tables:

- `findings_staging`: batch load target for one crawler run.
- `findings`: canonical upserted table keyed by `id`.
- `findings_sync_state`: persistent checkpoints for resumable backfill runs.

The DDL lives in [../sql/create_tables.sql](../sql/create_tables.sql). The upsert query lives in [../sql/merge_findings.sql](../sql/merge_findings.sql).

## Template Variables

Replace these placeholders before running SQL:

- `${PROJECT_ID}`: Google Cloud project id.
- `${DATASET}`: BigQuery dataset name, for example `w3goaudit`.
- `${LOCATION}`: BigQuery dataset location, for example `US` or `asia-southeast1`.

## Table Design

`findings` and `findings_staging` intentionally share the same columns so JSONL rows can be loaded into staging and merged without reshaping inside SQL.

Typed columns are used for fields that are likely to be filtered, grouped, searched, or joined:

- identity: `id`, `slug`
- classification: `kind`, `impact`
- source entities: `auditfirm_id`, `firm_name`, `protocol_id`, `protocol_name`
- report metadata: `report_date`, `source_link`, `github_link`, `pdf_link`, `pdf_page_from`
- scoring: `quality_score`, `general_score`
- crawler metadata: `source_payload_hash`, `crawled_at`, `loaded_at`

Nested or unstable Solodit response fragments are preserved as JSON:

- `auditfirm`
- `protocol`
- `issue_finders`
- `issue_tag_scores`
- `source_payload`

`finder_handles` is stored as `ARRAY<STRING>` because it is useful for filtering and aggregation.

## Partitioning And Clustering

Both tables are partitioned by `DATE(loaded_at)`.

Both tables are clustered by:

- `impact`
- `firm_name`
- `protocol_name`
- `report_date`

This keeps common dashboard and search queries cheaper without requiring ingestion-time partitions.

`findings_sync_state` is not partitioned because it stores only a small number
of checkpoint rows keyed by `state_name`.

## Upsert Semantics

`sql/merge_findings.sql` deduplicates staging rows by `id`, keeping the newest row by `crawled_at` and `loaded_at`.

Rows are inserted when `id` is new. Existing rows are updated only when `source_payload_hash` changes. This avoids rewriting unchanged rows during scheduled incremental crawls.

## Backfill Checkpointing

GitHub Actions scheduled runs use backfill mode with a BigQuery-backed
checkpoint. The workflow restores `findings_sync_state.state_name = 'backfill'`
before crawling and updates it only after the exported JSONL has been loaded and
merged successfully. If a run times out before load, the next run repeats the
same chunk instead of skipping unloaded pages.

## Next Mapper Contract

The mapper should convert each validated `Finding` into one JSON object matching the table schema:

- Dates must be `YYYY-MM-DD` or `null`.
- Timestamps must be RFC3339 strings acceptable to BigQuery.
- JSON columns may be emitted as JSON objects/arrays when using the BigQuery client API, or as JSON strings when loading newline-delimited JSON.
- `source_payload_hash` should be a stable hash of the normalized source payload.
- `crawled_at` should represent when Solodit was fetched.
- `loaded_at` should represent when the row is prepared for BigQuery loading.
