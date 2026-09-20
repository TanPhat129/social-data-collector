from app.domain.interfaces import SourceRepository
from app.schemas import Source


class SyncConfig:
    def __init__(self, source_repository: SourceRepository):
        self.source_repository = source_repository

    def execute(self) -> list[Source]:
        return self.source_repository.list_enabled()
