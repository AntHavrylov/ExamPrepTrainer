from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Exam Prep Trainer"
    environment: str = "development"

    database_url: str = "sqlite:///./prep.db"

    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    max_document_content_length: int = 20000
    max_sections_per_user: int = 50

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
