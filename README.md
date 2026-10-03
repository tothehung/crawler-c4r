# W3GoAudit Crawler

Python crawler for syncing Solodit findings into BigQuery.

## Knowledge Base Contract (Phase 1)

The opt-in [knowledge data contract v1](docs/knowledge-data-contract-v1.md)
defines source snapshots, shared evidence, finding/evidence links, processing
state and knowledge candidates. It includes generated JSON schemas, synthetic
examples and an additive BigQuery migration. Existing crawler commands continue
to use the legacy tables; the new migration is not applied automatically.

```powershell
py scripts/export_knowledge_contract.py --check
```

## Setup

The original eight-phase plan is preserved in [ROADMAP.md](ROADMAP.md).
Phase 5 also supports [repository context enrichment](PHASE5_CONTEXT.md).

Phase 6 adds [finding deduplication, resumable batch sweeps and quality reports](PHASE6.md).
Phase 7 adds [grounded, versioned knowledge for finding/evidence](PHASE7.md),
with review and export. Embeddings and retrieval are excluded from the revised scope.

Phase 5 adds [strict engine validation](PHASE5.md). Build the Go engine and run
`scripts/validate_evidence.py` to annotate stored evidence with parser diagnostics
and unambiguous function metadata while preserving its content and identity.

Phase 4 adds [live evidence resolution](PHASE4.md) for Markdown, GitHub files/diffs,
and Gists. `scripts/process_knowledge.py run` connects these resolvers to the
transactional pipeline; recorded HTTP mode supports offline verification.

Phase 3 adds [transactional knowledge processing](PHASE3.md): immutable snapshots,
versioned processing keys, fenced worker leases, atomic evidence/link/state writes,
bounded retries, and SQLite/BigQuery backends. The resolver input is an explicit
complete result manifest for manual integrations; phase 4 also supports live resolvers.

Phase 2 provides an [offline evidence benchmark](tests/fixtures/evidence_benchmark_v1/README.md)
with 35 real findings, reviewed target annotations, recorded HTTP responses and
separate synthetic controls. Run `py scripts/benchmark_evidence.py --output data/processed/evidence-current.json`
to compare the current candidate extractor with the saved baseline.

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

### Load Directly Into BigQuery

To crawl and automatically load/merge records into the canonical BigQuery `findings` table (like Solodit sync):

```powershell
py scripts\crawl_code4rena.py --load-bigquery
```

### GitHub Actions (Automated Cloud Crawling)

A dedicated GitHub Actions workflow is provided at `.github/workflows/crawl_code4rena.yml`:
- Runs automatically daily at `21:00 UTC` (or triggered manually via **Run workflow**).
- Resumes progress automatically using cached checkpoints.
- Reuses the existing GCP secrets (`BIGQUERY_PROJECT_ID`, `BIGQUERY_DATASET`, `BIGQUERY_LOCATION`, `GCP_SERVICE_ACCOUNT_JSON`).
- Automatically loads and merges findings into BigQuery without requiring a local machine running.

### Options Reference

- `--max-contests <N>`: Limit number of contests to process in this run.
- `--load-bigquery`: Automatically load and merge JSONL into BigQuery after crawling.
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
