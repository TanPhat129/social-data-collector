"""Facebook post-search workflow, deliberately independent of group assignments."""
from hashlib import sha1
from pathlib import Path
from urllib.parse import quote

import yaml
from pydantic import BaseModel, Field

from app.integrations.google_sheets import GoogleSheetsWriter
from app.orchestration.workers import BrowserAccountShardWorker, GoogleSheetsOutboxWorker
from app.processing.keyword_filter import KeywordFilter
from app.schemas import Source


class PostSearchSettings(BaseModel):
    enabled: bool = True
    queries: list[str] = Field(min_length=1)
    max_posts_per_query: int = Field(default=20, ge=1, le=100)
    account_ids: list[str] = Field(min_length=1)


def load_post_search(path: str) -> PostSearchSettings:
    values = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return PostSearchSettings.model_validate(values.get("facebook_post_search", values))


def post_search_sources(config: PostSearchSettings) -> list[Source]:
    return [Source(id=f"fb_search_{sha1(query.encode()).hexdigest()[:12]}", name=f"Facebook Search: {query}",
                   platform="facebook", source_url=f"https://www.facebook.com/search/posts/?q={quote(query)}")
            for query in config.queries]


def run_post_search(settings, container, account_id: str) -> tuple[int, int]:
    if not settings.postgres_dsn:
        raise ValueError("POSTGRES_DSN is required for Facebook post search")
    from app.database.postgres_coordinator import PostgresCoordinator
    from app.orchestration.yaml_config import YamlOrchestrationConfig

    document = YamlOrchestrationConfig(settings.account_pools_path).load()
    account = next((item for item in document.accounts if item.id == account_id), None)
    if account is None:
        raise ValueError(f"Unknown account: {account_id}")
    config = load_post_search(settings.post_search_path)
    if not config.enabled or account_id not in config.account_ids:
        raise ValueError(f"Account {account_id} is not enabled in post_search.yaml")
    sources = post_search_sources(config)
    store = PostgresCoordinator(settings.postgres_dsn)
    store.initialize_schema(); store.sync_yaml(document); store.register_runtime_sources(sources)
    classifier, extractor = container._ai_components()
    worker = BrowserAccountShardWorker(store, KeywordFilter.from_yaml(settings.keywords_path),
        headless=settings.facebook_browser_headless, max_posts=config.max_posts_per_query,
        max_scrolls=settings.facebook_browser_max_scrolls, classifier=classifier, extractor=extractor)
    outbox = GoogleSheetsOutboxWorker(store, GoogleSheetsWriter(settings.google_sheet_id, settings.google_service_account_file), settings.sheet_outbox_batch_size)
    accepted = 0
    try:
        accepted = worker.run(account, sources, settings.account_shard_timeout_seconds)
    except KeyboardInterrupt:
        while outbox.flush_once():
            pass
        raise
    exported = 0
    while count := outbox.flush_once():
        exported += count
    return accepted, exported
