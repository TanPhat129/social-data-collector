from datetime import datetime, timedelta
from app.collectors.base import BaseCollector
from app.schemas import RawPost, Source


class MockFacebookCollector(BaseCollector):
    """Development-only collector; replace with a permitted integration."""
    def collect(self, source: Source) -> list[RawPost]:
        return [RawPost(post_id=f"mock-{source.id}-001", source=source,
            content="Cần gia sư Toán lớp 8 tại Quận 3, học 2 buổi/tuần. Liên hệ 0901234567.",
            posted_at=datetime.now() - timedelta(minutes=15), post_url="https://example.invalid/posts/mock-001",
            author_url="https://example.invalid/profile/mock-author")]
