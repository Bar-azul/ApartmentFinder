from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "ApartmentFinder"

    yad2_base_url: str = "https://gw.yad2.co.il"

    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"

    playwright_enabled: bool = True
    playwright_headless: bool = False
    playwright_enrich_on_search: bool = True

    playwright_max_details_per_search: int = 100
    playwright_detail_concurrency: int = 3
    playwright_batch_size: int = 10
    playwright_batch_delay_seconds: float = 1.5

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()