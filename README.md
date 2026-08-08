# W3GoAudit Crawler

Python crawler for syncing Solodit findings into BigQuery.

## Setup

Create a local environment file:

```powershell
Copy-Item .env.example .env
```

Then set `CYFRIN_API_KEY` in `.env`.

## Local Sync

Backfill historical findings with checkpoint/resume:

```powershell
py scripts\sync.py backfill --page-size 50 --max-pages 50
```

Run the command again to continue from `data/checkpoints/findings_export.json`.
Omit `--max-pages` only when you intentionally want the current run to continue
until the Solodit API is exhausted.

Scan newest findings after backfill is complete:

```powershell
py scripts\sync.py incremental --page-size 50
```

Incremental mode starts from page 1, writes to
`data/findings_incremental.jsonl`, and relies on the BigQuery merge to insert new
records or update changed records without duplicating old findings.

## GitHub Actions

The workflow in `.github/workflows/crawl.yml` is ready for scheduled
incremental sync. It runs daily at `19:00 UTC` and can also be started manually
from the Actions tab.

Add these repository secrets before enabling the workflow:

```text
CYFRIN_API_KEY
GCP_SERVICE_ACCOUNT_JSON
BIGQUERY_PROJECT_ID
BIGQUERY_DATASET
BIGQUERY_LOCATION
```

Optional repository variables:

```text
SOLODIT_PAGE_SIZE=50
SOLODIT_INCREMENTAL_MAX_PAGES=10
SOLODIT_RATE_LIMIT_PER_MINUTE=20
SOLODIT_BASE_URL=https://solodit.cyfrin.io
```

Scheduled runs use incremental mode. Manual runs can choose `backfill`, but
GitHub-hosted runners do not preserve `data/checkpoints/findings_export.json`
between runs, so backfill in Actions is only appropriate for a bounded one-run
job unless checkpoint persistence is moved to BigQuery or GCS.
