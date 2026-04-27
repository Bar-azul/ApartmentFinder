from __future__ import annotations

import asyncio
import os
import uuid
from datetime import UTC, datetime
from typing import Any

from app.models.apartment import Apartment
from app.services.playwright_details_service import (
    CaptchaDetectedError,
    PlaywrightDetailsService,
)


class VerificationQueueStore:
    def __init__(self) -> None:
        self.jobs: dict[str, dict[str, Any]] = {}
        self.details_service = PlaywrightDetailsService()

    def _settings(self) -> tuple[int, int, float]:
        concurrency = int(os.getenv("VERIFY_BACKGROUND_CONCURRENCY", "3"))
        batch_size = int(os.getenv("VERIFY_BATCH_SIZE", "10"))
        delay_seconds = float(os.getenv("VERIFY_DELAY_SECONDS", "2.5"))
        return concurrency, batch_size, delay_seconds

    def create_job(
        self,
        apartments: list[dict[str, Any]],
        required_features: list[str],
    ) -> str:
        concurrency, batch_size, delay_seconds = self._settings()
        job_id = str(uuid.uuid4())

        self.jobs[job_id] = {
            "job_id": job_id,
            "status": "pending",
            "total": len(apartments),
            "checked": 0,
            "verified": 0,
            "rejected": 0,
            "failed": 0,
            "current_batch": 0,
            "batch_size": batch_size,
            "concurrency": concurrency,
            "delay_seconds": delay_seconds,
            "done": False,
            "fallback_mode": False,
            "fallback_message": None,
            "apartments": apartments,
            "verified_apartments": [],
            "candidate_apartments": [],
            "last_batch_apartments": [],
            "required_features": required_features,
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        }

        asyncio.create_task(self._run_job(job_id))
        return job_id

    def get(self, job_id: str) -> dict[str, Any] | None:
        return self.jobs.get(job_id)

    async def _run_job(self, job_id: str) -> None:
        job = self.jobs.get(job_id)
        if not job:
            return

        concurrency = job["concurrency"]
        batch_size = job["batch_size"]
        delay_seconds = job["delay_seconds"]

        raw_apartments: list[dict[str, Any]] = job["apartments"]
        required_features: list[str] = job["required_features"]

        job["status"] = "running"
        job["updated_at"] = datetime.now(UTC).isoformat()

        try:
            for start in range(0, len(raw_apartments), batch_size):
                batch_number = (start // batch_size) + 1
                raw_batch = raw_apartments[start:start + batch_size]

                job["current_batch"] = batch_number
                job["last_batch_apartments"] = []
                job["updated_at"] = datetime.now(UTC).isoformat()

                print(
                    f"VERIFY QUEUE batch={batch_number} "
                    f"items={len(raw_batch)} concurrency={concurrency}"
                )

                batch_apartments = [Apartment(**raw) for raw in raw_batch]

                enriched_batch = await self.details_service.enrich_batch_for_verification(
                    apartments=batch_apartments,
                    concurrency=concurrency,
                )

                batch_verified: list[dict[str, Any]] = []

                for apartment in enriched_batch:
                    job["checked"] += 1

                    if self._matches_required_features(apartment, required_features):
                        apartment.verification_status = "verified"
                        apartment.verification_reason = "המודעה אומתה ומתאימה"
                        apartment_dict = apartment.model_dump()

                        job["verified"] += 1
                        job["verified_apartments"].append(apartment_dict)
                        batch_verified.append(apartment_dict)
                    else:
                        job["rejected"] += 1

                job["last_batch_apartments"] = batch_verified
                job["updated_at"] = datetime.now(UTC).isoformat()

                if start + batch_size < len(raw_apartments):
                    await asyncio.sleep(delay_seconds)

            job["status"] = "done"
            job["done"] = True
            job["updated_at"] = datetime.now(UTC).isoformat()

        except CaptchaDetectedError as e:
            self._activate_fallback(job, str(e))

        except Exception as e:
            self._activate_fallback(job, f"Enrichment failed: {e}")

    def _activate_fallback(self, job: dict[str, Any], message: str) -> None:
        raw_apartments: list[dict[str, Any]] = job["apartments"]

        candidate_apartments = []

        for raw in raw_apartments:
            apartment = Apartment(**raw)
            apartment.verification_status = "unverified"
            apartment.verification_reason = (
                "לא הצלחנו לאמת מאפיינים מול יד2. "
                "המודעה מוצגת כמועמדת ולא בהכרח עומדת בכל מאפייני החובה."
            )
            candidate_apartments.append(apartment.model_dump())

        job["status"] = "fallback"
        job["done"] = True
        job["fallback_mode"] = True
        job["fallback_message"] = message
        job["candidate_apartments"] = candidate_apartments
        job["verified_apartments"] = candidate_apartments
        job["last_batch_apartments"] = candidate_apartments
        job["updated_at"] = datetime.now(UTC).isoformat()

        print(f"VERIFY QUEUE fallback activated: {message}")

    def _matches_required_features(
        self,
        apartment: Apartment,
        required_features: list[str],
    ) -> bool:
        if not required_features:
            return True

        return all(
            getattr(apartment.features, feature_name, False)
            for feature_name in required_features
        )


verification_queue_store = VerificationQueueStore()