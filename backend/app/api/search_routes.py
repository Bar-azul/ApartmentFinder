from fastapi import APIRouter, HTTPException

from app.models.search_filters import DirectSearchRequest, PromptSearchRequest
from app.services.llm_filter_parser import LLMFilterParser
from app.services.yad2_client import Yad2Client

router = APIRouter(prefix="/api/search", tags=["Search"])

yad2_client = Yad2Client()
llm_parser = LLMFilterParser()


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