import asyncio
import logging

from fastapi import APIRouter, HTTPException

from app.models.apartment import Apartment
from app.models.search_filters import DirectSearchRequest, PromptSearchRequest
from app.services.llm_filter_parser import LLMFilterParser
from app.services.playwright_details_service import PlaywrightDetailsService
from app.services.yad2_client import Yad2Client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/search", tags=["Search"])

yad2_client = Yad2Client()
llm_parser = LLMFilterParser()
details_service = PlaywrightDetailsService()


@router.post("/prompt")
async def search_by_prompt(request: PromptSearchRequest):
    try:
        filters = llm_parser.parse(request.prompt)
        apartments = await yad2_client.search_rentals(filters)

        return {
            "success": True,
            "filters": filters.model_dump(),
            "count": len(apartments),
            "apartments": [apartment.model_dump() for apartment in apartments],
        }

    except Exception as e:
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
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/details")
async def get_apartment_details(apartment: Apartment):
    try:
        enriched = await details_service.enrich_apartment(apartment)

        return {
            "success": True,
            "apartment": enriched.model_dump(),
        }

    except Exception as e:
        apartment.description = f"שגיאה בשליפת פרטים מלאים: {str(e)}"

        return {
            "success": False,
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