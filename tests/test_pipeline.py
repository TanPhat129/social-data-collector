from app.collectors.mock import MockFacebookCollector
from app.database.processed_posts import ProcessedPostStore
from app.integrations.google_sheets import GoogleSheetsWriter
from app.pipeline import LeadPipeline
from app.processing.keyword_filter import KeywordFilter
from app.schemas import Source


def test_pipeline_accepts_once(tmp_path):
    pipeline = LeadPipeline(
        MockFacebookCollector(),
        KeywordFilter(["cần gia sư"]),
        ProcessedPostStore(f"sqlite:///{tmp_path}/test.db"),
        GoogleSheetsWriter(),
    )
    source = Source(id="test", name="Test Group")
    assert len(pipeline.run(source)) == 1
    assert pipeline.run(source) == []


def test_offer_post_is_not_a_lead(tmp_path):
    from app.collectors.base import BaseCollector
    from app.schemas import RawPost

    class OfferCollector(BaseCollector):
        def collect(self, source):
            return [RawPost(post_id="offer", source=source, content="Nhận dạy Toán lớp 8, cần gia sư liên hệ em.")]

    pipeline = LeadPipeline(
        OfferCollector(), KeywordFilter(["cần gia sư"]),
        ProcessedPostStore(f"sqlite:///{tmp_path}/test.db"), GoogleSheetsWriter(),
    )
    assert pipeline.run(Source(id="test", name="Test Group")) == []


def test_pipeline_deduplicates_identical_content_across_post_ids(tmp_path):
    from app.collectors.base import BaseCollector
    from app.schemas import RawPost

    class DuplicateCollector(BaseCollector):
        def collect(self, source):
            return [
                RawPost(post_id="first", source=source, content="Cần gia sư Toán lớp 8.", post_url="https://facebook.example/posts/first"),
                RawPost(post_id="second", source=source, content="Cần   gia sư Toán lớp 8.", post_url="https://facebook.example/posts/second"),
            ]

    pipeline = LeadPipeline(
        DuplicateCollector(), KeywordFilter(["cần gia sư"]),
        ProcessedPostStore(f"sqlite:///{tmp_path}/test.db"), GoogleSheetsWriter(),
    )
    assert [lead.post_id for lead in pipeline.run(Source(id="test", name="Test Group"))] == ["first"]


def test_pipeline_exports_accepted_leads_as_one_batch(tmp_path):
    from app.collectors.base import BaseCollector
    from app.schemas import RawPost

    class TwoPosts(BaseCollector):
        def collect(self, source):
            return [
                RawPost(post_id=str(index), source=source, content=f"Cần gia sư Toán lớp {index}.", post_url=f"https://facebook.example/posts/{index}")
                for index in (7, 8)
            ]

    class BatchWriter:
        def __init__(self):
            self.batches = []

        def append_many(self, leads):
            self.batches.append(leads)

    writer = BatchWriter()
    pipeline = LeadPipeline(
        TwoPosts(), KeywordFilter(["cần gia sư"]),
        ProcessedPostStore(f"sqlite:///{tmp_path}/test.db"), writer,
    )
    assert len(pipeline.run(Source(id="test", name="Test Group"))) == 2
    assert [len(batch) for batch in writer.batches] == [2]


def test_pipeline_rejects_post_without_permalink(tmp_path):
    from app.collectors.base import BaseCollector
    from app.schemas import RawPost

    class NoPermalinkCollector(BaseCollector):
        def collect(self, source):
            return [RawPost(post_id="no-url", source=source, content="Cần gia sư Toán lớp 8.")]

    pipeline = LeadPipeline(
        NoPermalinkCollector(), KeywordFilter(["cần gia sư"]),
        ProcessedPostStore(f"sqlite:///{tmp_path}/test.db"), GoogleSheetsWriter(),
    )
    assert pipeline.run(Source(id="test", name="Test Group")) == []
