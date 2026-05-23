"""
Learning System
Stores incident history (problem → action → outcome) in SQLite
and provides success-rate statistics for improving future decisions.
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Optional


DB_PATH = Path(__file__).parent.parent.parent / "data" / "learning.db"


class LearningDB:
    """
    Persistent SQLite-backed store for incident records.
    The SimulationEngine can query historical success rates
    to adjust base probabilities over time.
    """

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    # ── Schema ───────────────────────────────────────────────────────────────

    def _init_db(self):
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS incidents (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    failure_id      TEXT,
                    timestamp       TEXT,
                    primary_metric  TEXT,
                    severity        TEXT,
                    action_taken    TEXT,
                    success         INTEGER,
                    confidence      REAL,
                    raw_metrics     TEXT,
                    explanation     TEXT,
                    notes           TEXT,
                    created_at      TEXT DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS action_stats (
                    action          TEXT,
                    metric          TEXT,
                    total           INTEGER DEFAULT 0,
                    successes       INTEGER DEFAULT 0,
                    PRIMARY KEY (action, metric)
                );
            """)

    def _conn(self):
        return sqlite3.connect(str(self.db_path))

    # ── Write ─────────────────────────────────────────────────────────────────

    def record_incident(
        self,
        failure_event: dict,
        decision_record: dict,
        outcome_success: bool,
        notes: str = "",
    ) -> int:
        """
        Store an incident and update action statistics.

        Returns:
            Row ID of the new incident record.
        """
        action = decision_record.get("action_taken") or "none"
        metric = failure_event.get("primary_metric", "unknown")

        with self._conn() as conn:
            cursor = conn.execute(
                """
                INSERT INTO incidents
                    (failure_id, timestamp, primary_metric, severity,
                     action_taken, success, confidence, raw_metrics, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    failure_event.get("id"),
                    failure_event.get("timestamp", datetime.utcnow().isoformat()),
                    metric,
                    failure_event.get("severity"),
                    action,
                    int(outcome_success),
                    decision_record.get("confidence", 0),
                    json.dumps(failure_event.get("raw_metrics", {})),
                    notes,
                ),
            )
            row_id = cursor.lastrowid

            # Upsert action stats
            conn.execute(
                """
                INSERT INTO action_stats (action, metric, total, successes)
                VALUES (?, ?, 1, ?)
                ON CONFLICT(action, metric) DO UPDATE SET
                    total = total + 1,
                    successes = successes + excluded.successes
                """,
                (action, metric, int(outcome_success)),
            )

        return row_id

    # ── Read ──────────────────────────────────────────────────────────────────

    def get_success_rate(self, action: str, metric: str) -> Optional[float]:
        """
        Return historical success rate for (action, metric) pair.
        Returns None if no data exists.
        """
        with self._conn() as conn:
            row = conn.execute(
                "SELECT total, successes FROM action_stats WHERE action=? AND metric=?",
                (action, metric),
            ).fetchone()

        if not row or row[0] == 0:
            return None
        return round(row[1] / row[0], 4)

    def get_recent_incidents(self, limit: int = 20) -> list[dict]:
        """Fetch the most recent incidents."""
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT failure_id, timestamp, primary_metric, severity,
                       action_taken, success, confidence, notes
                FROM incidents
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        cols = ["failure_id", "timestamp", "primary_metric", "severity",
                "action_taken", "success", "confidence", "notes"]
        return [dict(zip(cols, row)) for row in rows]

    def get_all_stats(self) -> list[dict]:
        """Return all action statistics."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT action, metric, total, successes FROM action_stats ORDER BY total DESC"
            ).fetchall()
        return [
            {
                "action": r[0],
                "metric": r[1],
                "total": r[2],
                "successes": r[3],
                "success_rate": round(r[3] / r[2], 4) if r[2] > 0 else 0,
            }
            for r in rows
        ]

    def get_summary(self) -> dict:
        with self._conn() as conn:
            total = conn.execute("SELECT COUNT(*) FROM incidents").fetchone()[0]
            resolved = conn.execute("SELECT COUNT(*) FROM incidents WHERE success=1").fetchone()[0]
        return {
            "total_incidents": total,
            "resolved": resolved,
            "unresolved": total - resolved,
            "resolution_rate": round(resolved / total, 4) if total > 0 else 0,
        }


# ── Quick self-test ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    db = LearningDB(db_path=Path("/tmp/test_learning.db"))

    fake_failure = {
        "id": "failure_001",
        "timestamp": "2024-01-15T10:23:45",
        "primary_metric": "memory_usage",
        "severity": "high",
        "raw_metrics": {"memory_usage": 92.5, "cpu_usage": 45.0},
    }
    fake_decision = {"action_taken": "scale_pods", "confidence": 0.85}

    db.record_incident(fake_failure, fake_decision, outcome_success=True, notes="Scaled to 5 pods")
    db.record_incident(fake_failure, fake_decision, outcome_success=False, notes="Scaling insufficient")

    print("Success rate:", db.get_success_rate("scale_pods", "memory_usage"))
    print("Recent:", json.dumps(db.get_recent_incidents(5), indent=2))
    print("Summary:", db.get_summary())
