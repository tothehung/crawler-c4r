"""Bounded BigQuery transactions with an optimistic, dataset-wide revision fence.

All mutations go through this backend. Conflicts abort the whole operation; the
caller can retry from fresh reads. Bootstrap migrations with workers stopped.
"""

from __future__ import annotations

import json
import re
from contextlib import contextmanager

from src.repositories.bigquery_repository import BigQueryFindingsRepository
from src.repositories.knowledge_store import KEYS, STORAGE_MODELS, validate_row


def column_expression(field: str, node: dict, definitions: dict) -> str:
    """Convert a canonical model JSON row to the generated typed SQL columns."""
    if "$ref" in node:
        node = definitions[node["$ref"].split("/")[-1]]
    if "anyOf" in node:
        choices = [c for c in node["anyOf"] if c.get("type") != "null"]
        if len(choices) == 1:
            return column_expression(field, choices[0], definitions)
        return f"JSON_QUERY(doc, '$.{field}')"
    value = f"JSON_VALUE(doc, '$.{field}')"
    kind = node.get("type")
    if kind == "object":
        return f"JSON_QUERY(doc, '$.{field}')"
    if kind == "array":
        item = node.get("items", {})
        if "$ref" in item:
            item = definitions[item["$ref"].split("/")[-1]]
        if item.get("type") in {"object", "array"} or "anyOf" in item:
            return f"JSON_QUERY(doc, '$.{field}')"
        return f"JSON_VALUE_ARRAY(doc, '$.{field}')"
    sql_type = {"integer": "INT64", "number": "FLOAT64", "boolean": "BOOL"}.get(kind)
    if node.get("format") == "date-time":
        sql_type = "TIMESTAMP"
    return f"CAST({value} AS {sql_type})" if sql_type else value


class BigQueryTransaction:
    def __init__(self, store, revision: int):
        self.store = store
        self.revision = revision
        self.writes = {}
        self.lease = None
        self.claim = None
        self.expired = None

    def get(self, table: str, key: str) -> dict | None:
        return self.writes.get((table, key)) or self.store.read(table, key)

    def put(self, table: str, row: dict) -> None:
        row = validate_row(table, row)
        self.writes[table, row[KEYS[table]]] = row

    def require_lease(self, state):
        self.lease = state

    def require_claim(self, state):
        self.claim = state

    def require_expired(self, state):
        self.expired = state

    def links(self, key: str) -> list[dict]:
        return self.store.links(key)

    def commit(self):
        if not self.writes:
            return
        sql = [
            "BEGIN TRANSACTION;",
            f"ASSERT (SELECT COUNT(*) = 1 FROM `{self.store.guard}` WHERE guard_id='v1') AS 'Invalid processing guard';",
            f"UPDATE `{self.store.guard}` SET revision=revision+1 WHERE guard_id='v1' AND revision=@revision;",
            "ASSERT @@row_count = 1 AS 'Knowledge revision conflict; retry operation';",
        ]
        params = [("revision", "INT64", self.revision)]
        if self.expired:
            sql.append(
                f"ASSERT (SELECT COUNT(*)=1 FROM `{self.store.table('evidence_processing_state')}` "
                "WHERE processing_key=@expired_key AND status='running' AND "
                "lease_expires_at<=CURRENT_TIMESTAMP()) AS 'Lease not expired';"
            )
            params.append(("expired_key", "STRING", self.expired.processing_key))
        if self.claim:
            sql.append(
                f"ASSERT (SELECT COUNT(*)=1 FROM `{self.store.table('evidence_processing_state')}` "
                "WHERE processing_key=@claim_key AND attempts<max_attempts AND (status='pending' "
                "OR (status='running' AND lease_expires_at<=CURRENT_TIMESTAMP()) "
                "OR (status IN ('partial','failed') AND retryable AND "
                "(next_retry_at IS NULL OR next_retry_at<=CURRENT_TIMESTAMP())))) AS 'Claim not eligible';"
            )
            params.append(("claim_key", "STRING", self.claim.processing_key))
        if self.lease:
            sql.append(
                f"ASSERT (SELECT COUNT(*)=1 FROM `{self.store.table('evidence_processing_state')}` "
                "WHERE processing_key=@lease_key AND status='running' AND lease_owner=@lease_owner "
                "AND attempts=@lease_attempt AND lease_expires_at>CURRENT_TIMESTAMP()) AS 'Lease lost';"
            )
            params.extend(
                [
                    ("lease_key", "STRING", self.lease.processing_key),
                    ("lease_owner", "STRING", self.lease.lease_owner),
                    ("lease_attempt", "INT64", self.lease.attempts),
                ]
            )
        for index, ((table, _), row) in enumerate(self.writes.items()):
            if table == "evidence_processing_state" and row["status"] == "running":
                sql.append(
                    f"ASSERT TIMESTAMP(JSON_VALUE(PARSE_JSON(@row_{index}), '$.lease_expires_at'))>CURRENT_TIMESTAMP() AS 'New lease already expired';"
                )
            schema = STORAGE_MODELS[table].model_json_schema()
            fields = list(schema["properties"])
            expressions = [
                f"{column_expression(field, node, schema.get('$defs', {}))} AS `{field}`"
                for field, node in schema["properties"].items()
            ]
            key = KEYS[table]
            select = ", ".join(expressions)
            update = ", ".join(f"`{field}`=s.`{field}`" for field in fields)
            columns = ", ".join(f"`{field}`" for field in fields)
            values = ", ".join(f"s.`{field}`" for field in fields)
            sql.append(
                f"MERGE `{self.store.table(table)}` t USING (SELECT {select} "
                f"FROM (SELECT PARSE_JSON(@row_{index}) AS doc)) s ON t.`{key}`=s.`{key}` "
                f"WHEN MATCHED THEN UPDATE SET {update} "
                f"WHEN NOT MATCHED THEN INSERT ({columns}) VALUES ({values});"
            )
            params.append(
                (f"row_{index}", "STRING", json.dumps(row, ensure_ascii=False))
            )
        sql.append("COMMIT TRANSACTION;")
        self.store.query("\n".join(sql), params)


class BigQueryKnowledgeStore:
    def __init__(self, *, project_id: str, dataset: str, location: str, client=None):
        if not re.fullmatch(r"[A-Za-z0-9_-]+", project_id) or not re.fullmatch(
            r"[A-Za-z0-9_]+", dataset
        ):
            raise ValueError("Invalid BigQuery project/dataset identifier")
        self.repository = BigQueryFindingsRepository(
            project_id=project_id,
            dataset=dataset,
            location=location,
            client=client,
        )
        self.guard = self.repository.table_id("knowledge_processing_guard")

    def table(self, table: str) -> str:
        if table not in KEYS:
            raise ValueError(table)
        return self.repository.table_id(table)

    def query(self, sql: str, params=()):
        bq = self.repository._bigquery_module()
        return list(
            self.repository.client.query(
                sql,
                location=self.repository.location,
                job_config=bq.QueryJobConfig(
                    query_parameters=[bq.ScalarQueryParameter(*p) for p in params]
                ),
            ).result()
        )

    @contextmanager
    def transaction(self):
        rows = self.query(f"SELECT revision FROM `{self.guard}` WHERE guard_id='v1'")
        if len(rows) != 1:
            raise RuntimeError(
                "Apply migration 002 with workers stopped; exactly one guard required"
            )
        tx = BigQueryTransaction(self, rows[0]["revision"])
        yield tx
        tx.commit()

    def read(self, table: str, key: str) -> dict | None:
        rows = self.query(
            f"SELECT TO_JSON_STRING(t) AS payload FROM `{self.table(table)}` t WHERE `{KEYS[table]}`=@key LIMIT 2",
            [("key", "STRING", key)],
        )
        if len(rows) > 1:
            raise RuntimeError(
                f"Duplicate identity in {table}; repair before processing"
            )
        return validate_row(table, json.loads(rows[0]["payload"])) if rows else None

    def states(self, *, after: str = "", limit: int = 100) -> list[dict]:
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        rows = self.query(
            f"SELECT TO_JSON_STRING(t) AS payload FROM `{self.table('evidence_processing_state')}` t "
            "WHERE processing_key>@after ORDER BY processing_key LIMIT @limit",
            [("after", "STRING", after), ("limit", "INT64", limit)],
        )
        return [
            validate_row("evidence_processing_state", json.loads(row["payload"]))
            for row in rows
        ]

    def links(self, key: str) -> list[dict]:
        rows = self.query(
            f"SELECT TO_JSON_STRING(t) AS payload FROM `{self.table('finding_evidence_links')}` t "
            "WHERE processing_key=@key ORDER BY link_id",
            [("key", "STRING", key)],
        )
        return [
            validate_row("finding_evidence_links", json.loads(row["payload"]))
            for row in rows
        ]

    def evidence(self, *, after: str = "", limit: int = 100) -> list[dict]:
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        rows = self.query(
            f"SELECT TO_JSON_STRING(t) AS payload FROM `{self.table('code_evidence')}` t "
            "WHERE evidence_id>@after ORDER BY evidence_id LIMIT @limit",
            [("after", "STRING", after), ("limit", "INT64", limit)],
        )
        return [
            validate_row("code_evidence", json.loads(row["payload"])) for row in rows
        ]

    def scan(self, table: str, *, after: str = "", limit: int = 100) -> list[dict]:
        if table not in KEYS or not 1 <= limit <= 1000:
            raise ValueError("Supported table and limit in 1..1000 required")
        rows = self.query(
            f"SELECT TO_JSON_STRING(t) AS payload FROM `{self.table(table)}` t "
            f"WHERE `{KEYS[table]}`>@after ORDER BY `{KEYS[table]}` LIMIT @limit",
            [("after", "STRING", after), ("limit", "INT64", limit)],
        )
        return [validate_row(table, json.loads(row["payload"])) for row in rows]
