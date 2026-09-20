from abc import ABC, abstractmethod
from app.schemas import RawPost, Source


class BaseCollector(ABC):
    @abstractmethod
    def collect(self, source: Source) -> list[RawPost]:
        """Return posts visible to the configured, permitted account."""

