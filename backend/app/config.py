from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "ApartmentFinder"

    yad2_base_url: str = "https://gw.yad2.co.il"

    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()