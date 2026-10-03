"""Transactional contract storage; SQLite is the offline/reference backend."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Protocol

from src.models.knowledge_base import KB_KEYS, KB_MODELS
from src.models.knowledge_contract import TABLE_MODELS
from src.models.knowledge_operations import OPERATIONS_KEYS, OPERATIONS_MODELS

STORAGE_MODELS = TABLE_MODELS | OPERATIONS_MODELS | KB_MODELS

KEYS = {
    "source_finding_snapshots": "snapshot_id",
    "code_evidence": "evidence_id",
    "finding_evidence_links": "link_id",
    "evidence_processing_state": "processing_key",
}
KEYS.update(OPERATIONS_KEYS)
KEYS.update(KB_KEYS)


class Transaction(Protocol):
    def get(self, table: str, key: str) -> dict | None: ...
    def put(self, table: str, row: dict) -> None: ...
    def links(self, key: str) -> list[dict]: ...


def validate_row(table: str, row: dict) -> dict:
    if table not in KEYS:
        raise ValueError(f"Unsupported processing table: {table}")
    return STORAGE_MODELS[table].model_validate(row).model_dump(mode="json")


class SQLiteTransaction:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def get(self, table: str, key: str) -> dict | None:
        if table not in KEYS:
            raise ValueError(table)
        record = self.connection.execute(
            "SELECT payload FROM records WHERE table_name = ? AND record_key = ?",
            (table, key),
        ).fetchone()
        return json.loads(record[0]) if record else None

    def put(self, table: str, row: dict) -> None:
        row = validate_row(table, row)
        self.connection.execute(
            "INSERT INTO records VALUES (?, ?, ?) "
            "ON CONFLICT(table_name, record_key) DO UPDATE SET payload=excluded.payload",
            (table, row[KEYS[table]], json.dumps(row, ensure_ascii=False)),
        )

    def links(self, key: str) -> list[dict]:
        rows = self.connection.execute(
            "SELECT payload FROM records WHERE table_name='finding_evidence_links' "
            "AND json_extract(payload, '$.processing_key')=? ORDER BY record_key",
            (key,),
        ).fetchall()
        return [json.loads(row[0]) for row in rows]


class SQLiteKnowledgeStore:
    """Each operation uses its own connection; BEGIN IMMEDIATE serializes claims."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS records ("
                "table_name TEXT NOT NULL, record_key TEXT NOT NULL, payload TEXT NOT NULL,"
                "PRIMARY KEY(table_name, record_key))"
            )

    @contextmanager
    def transaction(self):
        connection = sqlite3.connect(self.path, timeout=30)
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield SQLiteTransaction(connection)
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def read(self, table: str, key: str) -> dict | None:
        with self.transaction() as tx:
            return tx.get(table, key)

    def links(self, key: str) -> list[dict]:
        with self.transaction() as tx:
            return tx.links(key)

    def states(self, *, after: str = "", limit: int = 100) -> list[dict]:
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        with sqlite3.connect(self.path) as connection:
            rows = connection.execute(
                "SELECT payload FROM records WHERE table_name=? AND record_key>? "
                "ORDER BY record_key LIMIT ?",
                ("evidence_processing_state", after, limit),
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def evidence(self, *, after: str = "", limit: int = 100) -> list[dict]:
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        with sqlite3.connect(self.path) as connection:
            rows = connection.execute(
                "SELECT payload FROM records WHERE table_name='code_evidence' AND record_key>? "
                "ORDER BY record_key LIMIT ?",
                (after, limit),
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def scan(self, table: str, *, after: str = "", limit: int = 100) -> list[dict]:
        if table not in KEYS or not 1 <= limit <= 1000:
            raise ValueError("Supported table and limit in 1..1000 required")
        with sqlite3.connect(self.path) as connection:
            rows = connection.execute(
                "SELECT payload FROM records WHERE table_name=? AND record_key>? ORDER BY record_key LIMIT ?",
                (table, after, limit),
            ).fetchall()
        return [validate_row(table, json.loads(row[0])) for row in rows]
