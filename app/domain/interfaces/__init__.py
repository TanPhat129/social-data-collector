from typing import Protocol

from app.schemas import RawPost, Source, TutorLead


class PostCollector(Protocol):
    def collect(self, source: Source) -> list[RawPost]: ...


class LeadExporter(Protocol):
    def append_many(self, leads: list[TutorLead]) -> None: ...


class SourceRepository(Protocol):
    def list_enabled(self) -> list[Source]: ...


__all__ = ["LeadExporter", "PostCollector", "SourceRepository"]
