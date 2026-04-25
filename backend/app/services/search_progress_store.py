from __future__ import annotations

import uuid
from datetime import datetime, UTC
from typing import Any


class SearchProgressStore:
    def __init__(self) -> None:
        self.jobs: dict[str, dict[str, Any]] = {}

    def create_job(self) -> str:
        job_id = str(uuid.uuid4())

        self.jobs[job_id] = {
            "job_id": job_id,
            "progress": 0,
            "status": "מתחיל חיפוש...",
            "done": False,
            "success": None,
            "result": None,
            "error": None,
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        }

        return job_id

    def update(
        self,
        job_id: str,
        progress: int,
        status: str,
        result: Any | None = None,
        error: str | None = None,
        done: bool = False,
        success: bool | None = None,
    ) -> None:
        if job_id not in self.jobs:
            return

        self.jobs[job_id].update(
            {
                "progress": max(0, min(100, progress)),
                "status": status,
                "updated_at": datetime.now(UTC).isoformat(),
            }
        )

        if result is not None:
            self.jobs[job_id]["result"] = result

        if error is not None:
            self.jobs[job_id]["error"] = error

        if done:
            self.jobs[job_id]["done"] = True
            self.jobs[job_id]["success"] = success

    def get(self, job_id: str) -> dict[str, Any] | None:
        return self.jobs.get(job_id)


progress_store = SearchProgressStore()