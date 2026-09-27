"""Concrete account and Sheets workers used by the central orchestrator."""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from time import monotonic
from typing import Protocol

from app.collectors.facebook_browser import FacebookBrowserCollector
from app.integrations.google_sheets import GoogleSheetsWriter
from app.orchestration.models import ManagedAccount
from app.processing.classifier import TutorIntentClassifier
from app.processing.extractor import LeadExtractor
from app.processing.keyword_filter import KeywordFilter
from app.processing.validator import LeadValidator
from app.schemas import Source, TutorLead

logger = logging.getLogger(__name__)


class CentralPostStore(Protocol):
    def claim_post(self, post, account_id: str, content_hash: str) -> bool: ...
    def create_lead_and_outbox(self, lead: TutorLead) -> None: ...


class SheetOutboxStore(Protocol):
    def claim_sheet_outbox(self, limit: int) -> list[tuple[int, TutorLead]]: ...
    def mark_sheet_exported(self, outbox_ids: list[int]) -> None: ...
    def mark_sheet_retry(self, outbox_ids: list[int], error: str) -> None: ...


class BrowserAccountShardWorker:
    """Collect one account's assigned sources and write only to PostgreSQL.

    It intentionally never calls Google Sheets; that work belongs exclusively
    to ``GoogleSheetsOutboxWorker``.
    """
    def __init__(self, store: CentralPostStore, keywords: KeywordFilter, *, headless: bool,
                 max_posts: int, max_scrolls: int, classifier=None, extractor=None):
        self.store, self.keywords = store, keywords
        self.headless, self.max_posts, self.max_scrolls = headless, max_posts, max_scrolls
        self.classifier = classifier or TutorIntentClassifier()
        self.extractor = extractor or LeadExtractor()
        self.validator = LeadValidator()

    def run(self, account: ManagedAccount, sources: list[Source], timeout_seconds: int) -> int:
        started = monotonic()
        profile = Path(account.profile_path)
        if profile.name != account.facebook_uid:
            raise ValueError(f"Account {account.id} profile_path must end with its facebook_uid")
        collector = FacebookBrowserCollector(str(profile.parent), account.facebook_uid, headless=self.headless,
            max_posts=self.max_posts, max_scrolls=self.max_scrolls, allowed_account_uids={account.facebook_uid})
        accepted = 0
        for source in sources:
            if monotonic() - started >= timeout_seconds:
                raise TimeoutError(f"Account {account.id} exceeded shard timeout")
            for post in collector.collect(source):
                if monotonic() - started >= timeout_seconds:
                    raise TimeoutError(f"Account {account.id} exceeded shard timeout")
                # A canonical original-post URL is mandatory before a global
                # claim. Comments/replies and cards without an original URL do
                # not reach the database or downstream lead logic.
                if not post.post_url:
                    logger.debug("post_id=%s source=%s skipped=missing_post_url", post.post_id, source.id)
                    continue
                content_hash = hashlib.sha256(post.content.encode("utf-8")).hexdigest()
                if not self.store.claim_post(post, account.id, content_hash):
                    logger.debug("post_id=%s source=%s skipped=duplicate_global", post.post_id, source.id)
                    continue
                if not self.keywords.matches(post.content):
                    logger.debug("post_id=%s source=%s skipped=keyword_no_match", post.post_id, source.id)
                    continue
                result = self.classifier.classify(post.content)
                if result.intent != "FIND_TUTOR":
                    logger.debug("post_id=%s source=%s skipped=intent_%s", post.post_id, source.id, result.intent)
                    continue
                lead = self.extractor.extract(post, result.confidence)
                if not self.validator.validate(lead):
                    logger.debug("post_id=%s source=%s skipped=validation", post.post_id, source.id)
                    continue
                self.store.create_lead_and_outbox(lead)
                accepted += 1
        return accepted


class GoogleSheetsOutboxWorker:
    """The sole writer that exports pending central leads in outbox order."""
    def __init__(self, store: SheetOutboxStore, writer: GoogleSheetsWriter, batch_size: int = 50):
        self.store, self.writer, self.batch_size = store, writer, batch_size

    def flush_once(self) -> int:
        if not self.writer.sheet_id or not self.writer.service_account_file:
            raise RuntimeError("Google Sheets must be configured before the central outbox writer can export leads")
        entries = self.store.claim_sheet_outbox(self.batch_size)
        if not entries:
            return 0
        ids, leads = zip(*entries)
        try:
            self.writer.append_many(list(leads))
        except Exception as exc:
            self.store.mark_sheet_retry(list(ids), f"{type(exc).__name__}: {exc}")
            raise
        self.store.mark_sheet_exported(list(ids))
        return len(leads)
