from app.collectors.mock import MockFacebookCollector
from app.collectors.facebook_graph import FacebookGraphCollector
from app.collectors.facebook_browser import FacebookBrowserCollector
from app.config import Settings
from app.database.processed_posts import ProcessedPostStore
from app.integrations.google_sheets import GoogleSheetsWriter
from app.odoo.client import OdooClient
from app.odoo.source_service import SourceService
from app.pipeline import LeadPipeline
from app.processing.keyword_filter import KeywordFilter
from app.processing.extractor import LeadExtractor
from app.source_config import YamlSourceService
from app.use_cases.process_leads import ProcessLeads
from app.use_cases.sync_config import SyncConfig
from app.orchestration.orchestrator import ShardOrchestrator
from app.orchestration.runtime import CentralCrawlRuntime
from app.orchestration.workers import BrowserAccountShardWorker, GoogleSheetsOutboxWorker
from app.orchestration.yaml_config import YamlOrchestrationConfig
from app.database.postgres_coordinator import PostgresCoordinator


class Container:
    """Wires replaceable adapters. Mock collection is deliberate in development."""
    def __init__(self, settings: Settings):
        self.settings = settings
        if settings.app_env.lower() == "production":
            if settings.collector_provider not in {"facebook_graph", "facebook_browser"}:
                raise ValueError("Production requires a configured Facebook collector")
            if settings.ai_provider != "openai":
                raise ValueError("Production requires AI_PROVIDER=openai")
            if not all((settings.odoo_url, settings.odoo_db, settings.odoo_username, settings.odoo_password)):
                raise ValueError("Production requires complete Odoo configuration")
        self.pipeline: LeadPipeline | None = None

    def _legacy_pipeline(self) -> LeadPipeline:
        if self.pipeline is None:
            classifier, extractor = self._ai_components()
            self.pipeline = LeadPipeline(
                self._collector(),
                KeywordFilter.from_yaml(self.settings.keywords_path),
                ProcessedPostStore(self.settings.database_url),
                GoogleSheetsWriter(self.settings.google_sheet_id, self.settings.google_service_account_file),
                classifier=classifier, extractor=extractor,
            )
        return self.pipeline

    def _collector(self):
        if self.settings.collector_provider == "mock":
            return MockFacebookCollector()
        if self.settings.collector_provider == "facebook_graph":
            return FacebookGraphCollector(self.settings.facebook_access_token or "", self.settings.facebook_graph_api_version,
                self.settings.facebook_max_posts_per_source)
        if self.settings.collector_provider == "facebook_browser":
            allowed_uids = YamlSourceService(self.settings.source_config_path).allowed_account_uids()
            return FacebookBrowserCollector(self.settings.facebook_browser_profile_root, self.settings.facebook_browser_account_uid or "",
                headless=self.settings.facebook_browser_headless,
                max_posts=self.settings.facebook_max_posts_per_source,
                max_scrolls=self.settings.facebook_browser_max_scrolls, allowed_account_uids=allowed_uids)
        raise ValueError(f"Unsupported COLLECTOR_PROVIDER: {self.settings.collector_provider}")

    def _ai_components(self):
        if self.settings.ai_provider == "deterministic":
            return None, None
        if self.settings.ai_provider == "openai":
            if not self.settings.openai_api_key:
                raise ValueError("OPENAI_API_KEY is required when AI_PROVIDER=openai")
            from app.integrations.openai_tutor import OpenAIIntentClassifier, OpenAILeadExtractor, OpenAITutorAnalyzer
            analyzer = OpenAITutorAnalyzer(self.settings.openai_api_key, self.settings.openai_model, self.settings.ai_max_retries)
            return OpenAIIntentClassifier(analyzer), OpenAILeadExtractor(analyzer, LeadExtractor())
        raise ValueError(f"Unsupported AI_PROVIDER: {self.settings.ai_provider}")

    def process_leads(self) -> ProcessLeads:
        return ProcessLeads(self._legacy_pipeline())

    def sync_config(self) -> SyncConfig | None:
        required = (self.settings.odoo_url, self.settings.odoo_db, self.settings.odoo_username, self.settings.odoo_password)
        if not all(required):
            return SyncConfig(YamlSourceService(self.settings.source_config_path))
        client = OdooClient(*required)
        return SyncConfig(SourceService(client, self.settings.odoo_source_model,
            name_field=self.settings.odoo_source_name_field, platform_field=self.settings.odoo_source_platform_field,
            external_id_field=self.settings.odoo_source_external_id_field, enabled_field=self.settings.odoo_source_enabled_field))

    def central_runtime(self) -> CentralCrawlRuntime:
        """Wire the multi-account path; the legacy SQLite pipeline remains separate."""
        if not self.settings.postgres_dsn:
            raise ValueError("POSTGRES_DSN is required for multi-account orchestration")
        coordinator = PostgresCoordinator(self.settings.postgres_dsn)
        config = YamlOrchestrationConfig(self.settings.account_pools_path)
        classifier, extractor = self._ai_components()
        account_worker = BrowserAccountShardWorker(
            coordinator, KeywordFilter.from_yaml(self.settings.keywords_path),
            headless=self.settings.facebook_browser_headless,
            max_posts=self.settings.facebook_max_posts_per_source,
            max_scrolls=self.settings.facebook_browser_max_scrolls,
            classifier=classifier, extractor=extractor,
        )
        sheets_worker = GoogleSheetsOutboxWorker(
            coordinator,
            GoogleSheetsWriter(self.settings.google_sheet_id, self.settings.google_service_account_file),
            self.settings.sheet_outbox_batch_size,
        )
        return CentralCrawlRuntime(ShardOrchestrator(config, coordinator, account_worker), sheets_worker)
