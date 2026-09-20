from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_env: str = "development"
    database_url: str = "sqlite:///./data/social_tutor.db"
    keywords_path: str = "config/keywords.yaml"
    timezone: str = "Asia/Ho_Chi_Minh"
    odoo_url: str | None = None
    odoo_db: str | None = None
    odoo_username: str | None = None
    odoo_password: str | None = None
    google_sheet_id: str | None = None
    google_service_account_file: str | None = None
    collection_interval_minutes: int = 15
    odoo_source_model: str = "social.tutor.source"
    odoo_source_name_field: str = "name"
    odoo_source_platform_field: str = "platform"
    odoo_source_external_id_field: str = "facebook_group_id"
    odoo_source_enabled_field: str = "enabled"
    collector_provider: str = "mock"
    source_config_path: str = "config/sources.yaml"
    facebook_access_token: str | None = None
    facebook_graph_api_version: str = "v22.0"
    facebook_max_posts_per_source: int = 100
    facebook_browser_profile_root: str = ".secrets/facebook-profiles"
    facebook_browser_account_uid: str | None = None
    facebook_browser_headless: bool = True
    facebook_browser_max_scrolls: int = 2
    ai_provider: str = "deterministic"
    openai_api_key: str | None = None
    openai_model: str = "gpt-5-mini"
    ai_max_retries: int = 3


@lru_cache
def get_settings() -> Settings:
    return Settings()
