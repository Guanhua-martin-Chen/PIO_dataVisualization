from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


DB_PATH = Path("outputs") / "analyst_memory.sqlite3"


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS analyst_memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            workbook_id TEXT NOT NULL,
            sheet_name TEXT NOT NULL,
            question TEXT NOT NULL,
            focus_part TEXT,
            risk_level TEXT,
            answer TEXT NOT NULL,
            evidence_json TEXT NOT NULL,
            recommended_actions_json TEXT NOT NULL,
            follow_up_questions_json TEXT NOT NULL,
            used_tools_json TEXT NOT NULL,
            warnings_json TEXT NOT NULL,
            mode TEXT,
            model TEXT,
            filters_json TEXT NOT NULL,
            retrieved_context_json TEXT NOT NULL DEFAULT '[]'
        )
        """
    )
    _ensure_columns(connection)
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_analyst_memory_scope
        ON analyst_memory (workbook_id, sheet_name, created_at DESC)
        """
    )
    return connection


def _ensure_columns(connection: sqlite3.Connection) -> None:
    columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(analyst_memory)").fetchall()
    }
    if "retrieved_context_json" not in columns:
        connection.execute(
            """
            ALTER TABLE analyst_memory
            ADD COLUMN retrieved_context_json TEXT NOT NULL DEFAULT '[]'
            """
        )


def save_analyst_memory(record: dict[str, Any]) -> int:
    with _connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO analyst_memory (
                created_at,
                workbook_id,
                sheet_name,
                question,
                focus_part,
                risk_level,
                answer,
                evidence_json,
                recommended_actions_json,
                follow_up_questions_json,
                used_tools_json,
                warnings_json,
                mode,
                model,
                filters_json,
                retrieved_context_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record["createdAt"],
                record["workbookId"],
                record["sheetName"],
                record["question"],
                record.get("focusPart"),
                record.get("riskLevel"),
                record["answer"],
                json.dumps(record.get("evidence", []), ensure_ascii=False),
                json.dumps(record.get("recommendedActions", []), ensure_ascii=False),
                json.dumps(record.get("followUpQuestions", []), ensure_ascii=False),
                json.dumps(record.get("usedTools", []), ensure_ascii=False),
                json.dumps(record.get("warnings", []), ensure_ascii=False),
                record.get("mode"),
                record.get("model"),
                json.dumps(record.get("filters", {}), ensure_ascii=False),
                json.dumps(record.get("retrievedContext", []), ensure_ascii=False),
            ),
        )
        connection.commit()
        return int(cursor.lastrowid)


def list_analyst_memories(workbook_id: str, sheet_name: str, limit: int = 12) -> list[dict[str, Any]]:
    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM analyst_memory
            WHERE workbook_id = ? AND sheet_name = ?
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (workbook_id, sheet_name, limit),
        ).fetchall()

    memories: list[dict[str, Any]] = []
    for row in rows:
        memories.append(
            {
                "id": int(row["id"]),
                "createdAt": row["created_at"],
                "workbookId": row["workbook_id"],
                "sheetName": row["sheet_name"],
                "question": row["question"],
                "focusPart": row["focus_part"],
                "riskLevel": row["risk_level"],
                "answer": row["answer"],
                "evidence": json.loads(row["evidence_json"]),
                "recommendedActions": json.loads(row["recommended_actions_json"]),
                "followUpQuestions": json.loads(row["follow_up_questions_json"]),
                "usedTools": json.loads(row["used_tools_json"]),
                "warnings": json.loads(row["warnings_json"]),
                "mode": row["mode"],
                "model": row["model"],
                "filters": json.loads(row["filters_json"]),
                "retrievedContext": json.loads(row["retrieved_context_json"] or "[]"),
            }
        )
    return memories
