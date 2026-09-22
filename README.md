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

## Code4rena Crawler

Dedicated crawler for directly scraping all audited contest reports from Code4rena (`https://code4rena.com/reports`). No API key is required.

### Crawl All Contests

Crawl all available contests (~412 contests) with automated streaming to `data/findings_code4rena.jsonl` and checkpointing:

```powershell
py scripts\crawl_code4rena.py
```

If the process is interrupted, re-running the command will automatically continue from the last completed contest.

### Crawl In Batches

To crawl a specific number of contests (e.g. 10 contests):

```powershell
py scripts\crawl_code4rena.py --max-contests 10
```

### Filter By Severity

To extract only specific severities (e.g. High and Medium risk issues):

```powershell
py scripts\crawl_code4rena.py --severities "HIGH,MEDIUM"
```

### Options Reference

- `--max-contests <N>`: Limit number of contests to process in this run.
- `--reset`: Reset checkpoint and output file to start over from scratch.
- `--output <path>`: Custom output JSONL path (defaults to `data/findings_code4rena.jsonl`).
- `--checkpoint <path>`: Custom checkpoint file path (defaults to `data/checkpoints/code4rena_checkpoint.json`).
- `--severities <list>`: Comma-separated severities (`HIGH,MEDIUM,LOW,INFORMATIONAL,GAS`) or `all`.
- `--delay <sec>`: Delay in seconds between requests (defaults to `0.5`).


## GitHub Actions

The workflow in `.github/workflows/crawl.yml` is ready for scheduled
backfill sync. It runs daily at `19:00 UTC` and can also be started manually
from the Actions tab. Scheduled runs resume from the persistent checkpoint in
BigQuery, so each run continues from the last successfully loaded page.

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
SOLODIT_BACKFILL_MAX_PAGES=50
SOLODIT_INCREMENTAL_MAX_PAGES=10
SOLODIT_RATE_LIMIT_PER_MINUTE=20
SOLODIT_BASE_URL=https://solodit.cyfrin.io
SOLODIT_CHECKPOINT_BACKEND=bigquery
SOLODIT_CHECKPOINT_STATE_NAME=backfill
```

Scheduled runs use `backfill` mode by default. Each run crawls at most
`SOLODIT_PAGE_SIZE * SOLODIT_BACKFILL_MAX_PAGES` findings, loads them into
BigQuery, and then persists the next page in the `findings_sync_state` table.
Manual runs can still choose `incremental` to scan the newest pages from page 1.
