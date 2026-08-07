from __future__ import annotations

from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CREATE_TABLES_SQL_PATH = PROJECT_ROOT / "sql" / "create_tables.sql"
DEFAULT_MERGE_FINDINGS_SQL_PATH = PROJECT_ROOT / "sql" / "merge_findings.sql"


class BigQueryFindingsRepository:
    def __init__(
        self,
        *,
        project_id: str,
        dataset: str,
        location: str,
        client: Any | None = None,
    ) -> None:
        if not project_id:
            raise ValueError("project_id is required")
        if not dataset:
            raise ValueError("dataset is required")
        if not location:
            raise ValueError("location is required")

        self.project_id = project_id
        self.dataset = dataset
        self.location = location
        self.client = client or self._build_client(project_id=project_id, location=location)

    @property
    def staging_table_id(self) -> str:
        return self.table_id("findings_staging")

    @property
    def findings_table_id(self) -> str:
        return self.table_id("findings")

    def table_id(self, table_name: str) -> str:
        return f"{self.project_id}.{self.dataset}.{table_name}"

    def create_schema_and_tables(
        self,
        sql_path: Path = DEFAULT_CREATE_TABLES_SQL_PATH,
    ) -> None:
        self.execute_sql_file(sql_path)

    def truncate_staging_table(self) -> None:
        self.execute_sql(f"TRUNCATE TABLE `{self.staging_table_id}`")

    def load_jsonl_to_staging(self, jsonl_path: Path) -> int | None:
        bigquery = self._bigquery_module()
        job_config = bigquery.LoadJobConfig(
            source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
            write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        )

        with jsonl_path.open("rb") as source_file:
            load_job = self.client.load_table_from_file(
                source_file,
                self.staging_table_id,
                job_config=job_config,
                location=self.location,
            )
        load_job.result()
        return getattr(load_job, "output_rows", None)

    def merge_staging(
        self,
        sql_path: Path = DEFAULT_MERGE_FINDINGS_SQL_PATH,
    ) -> None:
        self.execute_sql_file(sql_path)

    def execute_sql_file(self, sql_path: Path) -> None:
        self.execute_sql(self.render_sql(sql_path.read_text(encoding="utf-8")))

    def execute_sql(self, sql: str) -> None:
        query_job = self.client.query(sql, location=self.location)
        query_job.result()

    def render_sql(self, sql: str) -> str:
        return (
            sql.replace("${PROJECT_ID}", self.project_id)
            .replace("${DATASET}", self.dataset)
            .replace("${LOCATION}", self.location)
        )

    @staticmethod
    def _build_client(*, project_id: str, location: str) -> Any:
        bigquery = BigQueryFindingsRepository._bigquery_module()
        return bigquery.Client(project=project_id, location=location)

    @staticmethod
    def _bigquery_module() -> Any:
        try:
            from google.cloud import bigquery
        except ImportError as exc:
            raise RuntimeError(
                "google-cloud-bigquery is required for BigQuery loading. "
                "Install project dependencies before running the load step."
            ) from exc
        return bigquery
