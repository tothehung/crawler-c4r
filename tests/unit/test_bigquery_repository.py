from __future__ import annotations

from typing import Any

from src.repositories.bigquery_repository import BigQueryFindingsRepository


class FakeQueryJob:
    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self.rows = rows or []
        self.result_called = False

    def result(self) -> list[dict[str, Any]]:
        self.result_called = True
        return self.rows


class FakeClient:
    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self.rows = rows or []
        self.queries: list[dict[str, Any]] = []
        self.last_query_job: FakeQueryJob | None = None

    def query(
        self,
        sql: str,
        *,
        job_config: Any | None = None,
        location: str | None = None,
    ) -> FakeQueryJob:
        self.queries.append(
            {
                "sql": sql,
                "job_config": job_config,
                "location": location,
            }
        )
        self.last_query_job = FakeQueryJob(self.rows)
        return self.last_query_job


class FakeBigQuery:
    class ScalarQueryParameter:
        def __init__(self, name: str, parameter_type: str, value: Any) -> None:
            self.name = name
            self.parameter_type = parameter_type
            self.value = value

    class QueryJobConfig:
        def __init__(self, query_parameters: list[Any]) -> None:
            self.query_parameters = query_parameters


def _repository(client: FakeClient) -> BigQueryFindingsRepository:
    return BigQueryFindingsRepository(
        project_id="project",
        dataset="dataset",
        location="US",
        client=client,
    )


def test_read_findings_checkpoint_returns_state(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        BigQueryFindingsRepository,
        "_bigquery_module",
        staticmethod(lambda: FakeBigQuery),
    )
    client = FakeClient(
        rows=[
            {
                "next_page": 5,
                "last_completed_page": 4,
                "pages_written": 4,
                "records_written": 200,
                "total_pages": 100,
                "completed": False,
            }
        ]
    )

    checkpoint = _repository(client).read_findings_checkpoint(state_name="backfill")

    assert checkpoint == {
        "next_page": 5,
        "last_completed_page": 4,
        "pages_written": 4,
        "records_written": 200,
        "total_pages": 100,
        "completed": False,
    }
    assert "`project.dataset.findings_sync_state`" in client.queries[0]["sql"]
    assert client.queries[0]["location"] == "US"
    parameters = client.queries[0]["job_config"].query_parameters
    assert parameters[0].name == "state_name"
    assert parameters[0].value == "backfill"


def test_write_findings_checkpoint_upserts_state(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        BigQueryFindingsRepository,
        "_bigquery_module",
        staticmethod(lambda: FakeBigQuery),
    )
    client = FakeClient()
    checkpoint = {
        "next_page": 7,
        "last_completed_page": 6,
        "pages_written": 6,
        "records_written": 300,
        "total_pages": 100,
        "completed": False,
    }

    _repository(client).write_findings_checkpoint(checkpoint, state_name="backfill")

    assert "MERGE `project.dataset.findings_sync_state`" in client.queries[0]["sql"]
    assert client.queries[0]["location"] == "US"
    assert client.last_query_job is not None
    assert client.last_query_job.result_called is True
    parameters = {
        parameter.name: parameter.value
        for parameter in client.queries[0]["job_config"].query_parameters
    }
    assert parameters["state_name"] == "backfill"
    assert parameters["next_page"] == 7
    assert parameters["last_completed_page"] == 6
    assert parameters["pages_written"] == 6
    assert parameters["records_written"] == 300
    assert parameters["total_pages"] == 100
    assert parameters["completed"] is False
