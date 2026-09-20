import logging

from app.collectors.base import BaseCollector
from app.database.processed_posts import ProcessedPostStore
from app.integrations.google_sheets import GoogleSheetsWriter
from app.processing.classifier import TutorIntentClassifier
from app.processing.extractor import LeadExtractor
from app.processing.keyword_filter import KeywordFilter
from app.processing.validator import LeadValidator
from app.schemas import Source, TutorLead

logger = logging.getLogger(__name__)


class LeadPipeline:
    def __init__(self, collector: BaseCollector, keywords: KeywordFilter, store: ProcessedPostStore, writer: GoogleSheetsWriter,
                 classifier=None, extractor=None):
        self.collector, self.keywords, self.store, self.writer = collector, keywords, store, writer
        self.classifier = classifier or TutorIntentClassifier()
        self.extractor = extractor or LeadExtractor()
        self.validator = LeadValidator()

    def run(self, source: Source) -> list[TutorLead]:
        accepted = []
        accepted_hashes: set[str] = set()
        for post in self.collector.collect(source):
            content_hash = self.store.content_hash(post.content)
            if content_hash in accepted_hashes:
                logger.debug("post_id=%s source=%s post_url=%s skipped=duplicate_in_batch", post.post_id, source.id, post.post_url or "missing")
                continue
            if self.store.seen(post.post_id, post.content):
                logger.debug("post_id=%s source=%s post_url=%s skipped=already_processed", post.post_id, source.id, post.post_url or "missing")
                continue
            if not self.keywords.matches(post.content):
                preview = " ".join(post.content.split())[:240]
                logger.debug("post_id=%s source=%s post_url=%s skipped=keyword_no_match content_preview=%r",
                    post.post_id, source.id, post.post_url or "missing", preview)
                continue
            result = self.classifier.classify(post.content)
            if result.intent != "FIND_TUTOR":
                logger.debug("post_id=%s source=%s post_url=%s skipped=intent_%s", post.post_id, source.id, post.post_url or "missing", result.intent)
                continue
            lead = self.extractor.extract(post, result.confidence)
            if not self.validator.validate(lead):
                logger.debug("post_id=%s source=%s post_url=%s skipped=validation", post.post_id, source.id, post.post_url or "missing")
                continue
            accepted.append(lead)
            accepted_hashes.add(content_hash)
            logger.debug("post_id=%s source=%s post_url=%s accepted", post.post_id, source.id, post.post_url or "missing")
        self.writer.append_many(accepted)
        for lead in accepted:
            self.store.mark(lead.post_id, lead.content)
        return accepted
