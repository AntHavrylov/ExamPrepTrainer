from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Exam Prep Trainer"
    environment: str = "development"

    database_url: str = "sqlite:///./prep.db"

    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 14

    max_document_content_length: int = 20000
    max_sections_per_user: int = 50

    openrouter_api_key: str = ""
    openrouter_model: str = "openai/gpt-oss-120b:free"

    max_questions_per_generate: int = 20
    max_generation_context_chars: int = 12000
    question_bank_batch_size: int = 5

    ai_rate_limit_max_requests: int = 30
    ai_rate_limit_window_seconds: int = 60

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
