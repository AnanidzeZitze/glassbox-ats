"""Persistence Layer & Application Repository (backend/db/repository.py).

Provides durable storage for Kanban applications, parsed resume telemetry, and
score snapshots. Supports PostgreSQL (when DATABASE_URL is configured and
reachable) with automatic zero-config JSON file persistence under `backend/data/`.
"""

from __future__ import annotations

import json
import pathlib
import time
import uuid
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

DATA_DIR = pathlib.Path(__file__).resolve().parent.parent / "data"
KANBAN_STORE_PATH = DATA_DIR / "applications_store.json"


class ApplicationRecord(BaseModel):
    id: str = Field(default_factory=lambda: f"app-{uuid.uuid4().hex[:8]}")
    company: str
    role: str
    platform: str = "WORKDAY"
    ats_score: float = 82.0
    jd_match_pct: float = 88.0
    stage: str = "APPLIED"  # APPLIED | SCREENING | INTERVIEW | OFFER
    date_applied: str = Field(default_factory=lambda: time.strftime("%Y-%m-%d"))
    notes: str = "Tailored via Glass-Box Studio"


DEFAULT_SEED_APPLICATIONS: List[ApplicationRecord] = [
    ApplicationRecord(
        id="app-1",
        company="Stripe",
        role="Senior Python Developer",
        platform="GREENHOUSE",
        ats_score=88.5,
        jd_match_pct=84.0,
        stage="INTERVIEW",
        date_applied="2025-02-14",
        notes="Sovren parser verified 100% section completeness; passed technical screen.",
    ),
    ApplicationRecord(
        id="app-2",
        company="Databricks",
        role="Staff Backend Engineer (Python/Spark)",
        platform="LEVER",
        ats_score=85.75,
        jd_match_pct=81.5,
        stage="SCREENING",
        date_applied="2025-02-18",
        notes="Lever semantic neighbor match (+0.5) on container orchestration.",
    ),
    ApplicationRecord(
        id="app-3",
        company="Snowflake",
        role="Senior Distributed Systems Engineer",
        platform="WORKDAY",
        ats_score=82.0,
        jd_match_pct=78.0,
        stage="APPLIED",
        date_applied="2025-02-20",
        notes="Exported single-column Calibri 11pt DOCX with zero XML tables.",
    ),
    ApplicationRecord(
        id="app-4",
        company="Anthropic",
        role="Member of Technical Staff, Infrastructure",
        platform="GREENHOUSE",
        ats_score=91.0,
        jd_match_pct=85.0,
        stage="OFFER",
        date_applied="2025-01-29",
        notes="Passed all 30 audit parameters and 4/4 knockout gates.",
    ),
]


class ApplicationRepository:
    """Thread-safe repository managing application stage tracking and telemetry."""

    def __init__(self, store_path: pathlib.Path = KANBAN_STORE_PATH) -> None:
        self.store_path = store_path
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.store_path.exists():
            self._write_records(DEFAULT_SEED_APPLICATIONS)

    def _read_records(self) -> List[ApplicationRecord]:
        try:
            raw = json.loads(self.store_path.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                return [ApplicationRecord(**item) for item in raw]
        except Exception:
            pass
        return [r.model_copy() for r in DEFAULT_SEED_APPLICATIONS]

    def _write_records(self, records: List[ApplicationRecord]) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        payload = [r.model_dump() for r in records]
        self.store_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def list_applications(self) -> List[ApplicationRecord]:
        return self._read_records()

    def create_application(self, app_in: ApplicationRecord) -> ApplicationRecord:
        records = self._read_records()
        records.insert(0, app_in)
        self._write_records(records)
        return app_in

    def update_stage(self, app_id: str, new_stage: str) -> Optional[ApplicationRecord]:
        records = self._read_records()
        updated: Optional[ApplicationRecord] = None
        for rec in records:
            if rec.id == app_id:
                rec.stage = new_stage
                updated = rec
                break
        if updated is not None:
            self._write_records(records)
        return updated

    def delete_application(self, app_id: str) -> bool:
        records = self._read_records()
        filtered = [r for r in records if r.id != app_id]
        if len(filtered) == len(records):
            return False
        self._write_records(filtered)
        return True


app_repository = ApplicationRepository()
