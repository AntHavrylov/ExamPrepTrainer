from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Exam Prep Trainer"
    environment: str = "development"

    database_url: str = "sqlite:///./prep.db"

    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 14

    api_key_encryption_key: str

    max_document_content_length: int = 50000
    max_sections_per_user: int = 50

    max_questions_per_generate: int = 20
    max_generation_context_chars: int = 12000
    question_bank_batch_size: int = 5
    background_question_batch_size: int = 2
    # Whether a training session may trigger AI generation itself (on-the-fly
    # fallback when the pool is dry, plus speculative background top-up).
    # Off by default so generation only ever happens explicitly, from the
    # Question Bank tab - keeps the (slow, rate-limited) AI calls fully under
    # the user's control instead of firing mid-session.
    live_question_generation_enabled: bool = False

    ai_rate_limit_max_requests: int = 30
    ai_rate_limit_window_seconds: int = 60

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
