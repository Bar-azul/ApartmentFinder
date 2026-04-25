from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.search_routes import router as search_router
from app.config import settings

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(search_router)


@app.get("/")
def health_check():
    return {
        "status": "ok",
        "app": settings.app_name,
    }