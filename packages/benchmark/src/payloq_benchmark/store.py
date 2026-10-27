"""SQLite metrics store under runs/ (portable, no server)."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SCHEMA = """
CREATE TABLE IF NOT EXISTS benchmark_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  batch_id TEXT NOT NULL,
  created_at TEXT NOT NULL,
  model TEXT NOT NULL,
  adapter TEXT,
  scenario_id TEXT NOT NULL,
  latency_ms REAL,
  tokens_in INTEGER,
  tokens_out INTEGER,
  hardware TEXT,
  parameter_score REAL,
  reading_score REAL,
  mom_score REAL,
  interpretation_score REAL,
  judge_score REAL,
  rough_cost_eur REAL,
  notes TEXT,
  detail_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_benchmark_runs_batch ON benchmark_runs(batch_id);
CREATE INDEX IF NOT EXISTS idx_benchmark_runs_model ON benchmark_runs(model);
"""


class MetricsStore:
    """Lightweight SQLite store for benchmark scorecards."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            conn.executescript(SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def insert_run(
        self,
        *,
        batch_id: str,
        model: str,
        scenario_id: str,
        adapter: str | None = None,
        latency_ms: float | None = None,
        tokens_in: int | None = None,
        tokens_out: int | None = None,
        hardware: str | None = None,
        parameter_score: float | None = None,
        reading_score: float | None = None,
        mom_score: float | None = None,
        interpretation_score: float | None = None,
        judge_score: float | None = None,
        rough_cost_eur: float | None = None,
        notes: str = "",
        detail: dict[str, Any] | None = None,
        created_at: str | None = None,
    ) -> int:
        created_at = created_at or datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO benchmark_runs (
                  batch_id, created_at, model, adapter, scenario_id,
                  latency_ms, tokens_in, tokens_out, hardware,
                  parameter_score, reading_score, mom_score,
                  interpretation_score, judge_score, rough_cost_eur,
                  notes, detail_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    batch_id,
                    created_at,
                    model,
                    adapter,
                    scenario_id,
                    latency_ms,
                    tokens_in,
                    tokens_out,
                    hardware,
                    parameter_score,
                    reading_score,
                    mom_score,
                    interpretation_score,
                    judge_score,
                    rough_cost_eur,
                    notes,
                    json.dumps(detail or {}, ensure_ascii=False),
                ),
            )
            conn.commit()
            return int(cur.lastrowid)

    def insert_many(self, rows: Iterable[dict[str, Any]], *, batch_id: str) -> int:
        n = 0
        for row in rows:
            self.insert_run(batch_id=batch_id, **row)
            n += 1
        return n

    def summary_by_model(self, batch_id: str) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT model,
                       COUNT(*) AS n,
                       AVG(parameter_score) AS avg_parameter,
                       AVG(reading_score) AS avg_reading,
                       AVG(mom_score) AS avg_mom,
                       AVG(interpretation_score) AS avg_interpretation,
                       AVG(judge_score) AS avg_judge,
                       AVG(latency_ms) AS avg_latency_ms,
                       SUM(COALESCE(tokens_in,0) + COALESCE(tokens_out,0)) AS tokens_total,
                       SUM(COALESCE(rough_cost_eur,0)) AS cost_eur
                FROM benchmark_runs
                WHERE batch_id = ?
                GROUP BY model
                ORDER BY model
                """,
                (batch_id,),
            ).fetchall()
        return [dict(r) for r in rows]
