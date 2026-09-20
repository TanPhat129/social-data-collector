from app.domain.interfaces import PostCollector
from app.schemas import RawPost, Source


class CollectPosts:
    def __init__(self, collector: PostCollector):
        self.collector = collector

    def execute(self, source: Source) -> list[RawPost]:
        return self.collector.collect(source)
