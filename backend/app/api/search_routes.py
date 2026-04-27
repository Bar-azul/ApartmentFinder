import asyncio
import logging

from fastapi import APIRouter, HTTPException

from app.models.apartment import Apartment
from app.models.search_filters import DirectSearchRequest, PromptSearchRequest
from app.services.llm_filter_parser import LLMFilterParser
from app.services.playwright_details_service import PlaywrightDetailsService
from app.services.search_progress_store import progress_store
from app.services.verification_queue_store import verification_queue_store
from app.services.yad2_client import Yad2Client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/search", tags=["Search"])

yad2_client = Yad2Client()
llm_parser = LLMFilterParser()
details_service = PlaywrightDetailsService()


@router.post("/start")
async def start_search(request: PromptSearchRequest):
    job_id = progress_store.create_job()

    asyncio.create_task(
        _run_search_job(
            job_id=job_id,
            prompt=request.prompt,
            selected_must_have=request.must_have or [],
        )
    )

    return {
        "success": True,
        "job_id": job_id,
    }


@router.get("/progress/{job_id}")
async def get_search_progress(job_id: str):
    job = progress_store.get(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return job


async def _run_search_job(
    job_id: str,
    prompt: str,
    selected_must_have: list[str] | None = None,
):
    try:
        progress_store.update(job_id, 5, "מנתח את הבקשה שלך...")

        filters = llm_parser.parse(
            prompt=prompt,
            selected_must_have=selected_must_have or [],
        )

        progress_store.update(job_id, 15, "מחפש מודעות ב־Yad2 Map API...")

        async def progress_callback(progress: int, status: str):
            progress_store.update(job_id, progress, status)

        apartments = await yad2_client.search_rentals(
            filters=filters,
            progress_callback=progress_callback,
        )

        result = {
            "success": True,
            "filters": filters.model_dump(),
            "count": len(apartments),
            "apartments": [apartment.model_dump() for apartment in apartments],
            "verification": {
                "required": True,
                "required_features": filters.must_have or [],
                "mode": "background_queue",
                "message": "התוצאות יאומתו ברקע ויוצגו רק לאחר אימות.",
            },
        }

        progress_store.update(
            job_id,
            100,
            "החיפוש הסתיים. מתחילים אימות ברקע...",
            result=result,
            done=True,
            success=True,
        )

    except Exception as e:
        logger.exception("Search job failed: %s", e)

        progress_store.update(
            job_id,
            100,
            "שגיאה במהלך החיפוש",
            error=str(e),
            done=True,
            success=False,
        )


@router.post("/prompt")
async def search_by_prompt(request: PromptSearchRequest):
    try:
        filters = llm_parser.parse(
            prompt=request.prompt,
            selected_must_have=request.must_have or [],
        )

        apartments = await yad2_client.search_rentals(filters)

        return {
            "success": True,
            "filters": filters.model_dump(),
            "count": len(apartments),
            "apartments": [apartment.model_dump() for apartment in apartments],
            "verification": {
                "required": True,
                "required_features": filters.must_have or [],
                "mode": "background_queue",
            },
        }

    except Exception as e:
        logger.exception("Prompt search failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/direct")
async def search_direct(request: DirectSearchRequest):
    try:
        apartments = await yad2_client.search_rentals(request.filters)

        return {
            "success": True,
            "filters": request.filters.model_dump(),
            "count": len(apartments),
            "apartments": [apartment.model_dump() for apartment in apartments],
            "verification": {
                "required": True,
                "required_features": request.filters.must_have or [],
                "mode": "background_queue",
            },
        }

    except Exception as e:
        logger.exception("Direct search failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/verify/start")
async def start_background_verification(payload: dict):
    apartments = payload.get("apartments") or []
    required_features = payload.get("required_features") or []

    if not apartments:
        raise HTTPException(status_code=400, detail="No apartments provided")

    job_id = verification_queue_store.create_job(
        apartments=apartments,
        required_features=required_features,
    )

    return {
        "success": True,
        "job_id": job_id,
    }


@router.get("/verify/progress/{job_id}")
async def get_background_verification_progress(job_id: str):
    job = verification_queue_store.get(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Verification job not found")

    return job


@router.post("/details")
async def get_apartment_details(apartment: Apartment):
    try:
        enriched = await details_service.enrich_apartment(apartment)

        return {
            "success": True,
            "apartment": enriched.model_dump(),
        }

    except Exception as e:
        logger.exception("Details enrichment failed: %s", e)

        apartment.description = f"שגיאה בשליפת פרטים מלאים: {str(e)}"

        return {
            "success": False,
            "error": str(e),
            "apartment": apartment.model_dump(),
        }


@router.post("/verify-one")
async def verify_one_apartment(apartment: Apartment):
    try:
        required_features = apartment.required_features or []

        apartment.verification_status = "checking"
        apartment.verification_reason = "בודק מאפיינים מול עמוד המודעה"

        enriched = await details_service.enrich_apartment(apartment)

        if not required_features:
            enriched.verification_status = "verified"
            enriched.verification_reason = "המודעה עברה העשרה ואימות"

            return {
                "success": True,
                "matched": True,
                "apartment": enriched.model_dump(),
            }

        missing_features = [
            feature_name
            for feature_name in required_features
            if not getattr(enriched.features, feature_name, False)
        ]

        if missing_features:
            enriched.verification_status = "rejected"
            enriched.verification_reason = "המודעה לא כוללת את כל מאפייני החובה"

            return {
                "success": True,
                "matched": False,
                "missing_features": missing_features,
                "apartment": enriched.model_dump(),
            }

        enriched.verification_status = "verified"
        enriched.verification_reason = "המודעה אומתה ומתאימה לכל מאפייני החובה"

        return {
            "success": True,
            "matched": True,
            "missing_features": [],
            "apartment": enriched.model_dump(),
        }

    except Exception as e:
        logger.exception("Lazy apartment verification failed: %s", e)

        apartment.verification_status = "failed"
        apartment.verification_reason = f"שגיאה באימות המודעה: {str(e)}"

        return {
            "success": False,
            "matched": False,
            "error": str(e),
            "apartment": apartment.model_dump(),
        }


async def _open_browser_safe(apartment: Apartment):
    try:
        await details_service.open_apartment_page(apartment)
    except Exception as e:
        logger.exception("Failed to open Yad2 browser page: %s", e)


@router.post("/open-browser")
async def open_apartment_in_browser(apartment: Apartment):
    asyncio.create_task(_open_browser_safe(apartment))

    return {
        "success": True,
        "message": "פותח את המודעה בדפדפן",
    }