from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    public_base_url: str = "http://localhost:8000"
    database_url: str = "sqlite:///./gprm.db"
    admin_token: str = "change-me"

    meta_api_version: str = "vXX.X"
    meta_access_token: str = ""
    meta_ig_user_id: str = ""
    meta_verify_token: str = "change-me-meta-verify"
    meta_app_secret: str = ""

    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    telegram_webhook_secret: str = "change-me-telegram-secret"
    allowed_operator_ids: str = ""  # comma-separated Telegram user IDs authorized to approve/reject/edit

    openai_api_key: str = ""
    openai_model: str = ""

    dm_reply_window_hours: int = 24
    comment_review_ttl_hours: int = 168
    daily_pulse_hour_utc: int = 8
    baseline_followers: int = 219
    target_followers: int = 1000

    @property
    def meta_base_url(self) -> str:
        return f"https://graph.instagram.com/{self.meta_api_version}"

    @property
    def allowed_operator_id_set(self) -> set[str]:
        return {x.strip() for x in self.allowed_operator_ids.split(",") if x.strip()}

    def validate_production(self) -> None:
        if self.app_env != "production":
            return
        errors: list[str] = []
        if self.database_url.startswith("sqlite"):
            errors.append("DATABASE_URL must use Postgres in production")
        if not self.public_base_url.startswith("https://") or "localhost" in self.public_base_url:
            errors.append("PUBLIC_BASE_URL must be a public HTTPS URL in production")
        if not self.meta_app_secret:
            errors.append("META_APP_SECRET is required")
        if not self.meta_access_token:
            errors.append("META_ACCESS_TOKEN is required")
        if not self.meta_ig_user_id:
            errors.append("META_IG_USER_ID is required")
        if not self.meta_api_version or self.meta_api_version == "vXX.X":
            errors.append("META_API_VERSION must be set to a supported version")
        if not self.allowed_operator_id_set:
            errors.append("ALLOWED_OPERATOR_IDS is required")
        if not self.telegram_bot_token:
            errors.append("TELEGRAM_BOT_TOKEN is required")
        if not self.telegram_chat_id:
            errors.append("TELEGRAM_CHAT_ID is required")
        defaults = {
            "ADMIN_TOKEN": (self.admin_token, "change-me"),
            "META_VERIFY_TOKEN": (self.meta_verify_token, "change-me-meta-verify"),
            "TELEGRAM_WEBHOOK_SECRET": (self.telegram_webhook_secret, "change-me-telegram-secret"),
        }
        for name, (value, insecure_default) in defaults.items():
            if not value or value == insecure_default or len(value) < 20:
                errors.append(f"{name} must be a non-default secret of at least 20 characters")
        if errors:
            raise RuntimeError("Unsafe production configuration: " + "; ".join(errors))


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.validate_production()
    return settings
