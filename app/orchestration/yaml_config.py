from collections import defaultdict
from pathlib import Path

import yaml

from app.orchestration.models import AccountPool, ManagedAccount, OrchestrationDocument, SourceAssignment
from app.schemas import Source


class YamlOrchestrationConfig:
    """Loads the operator-maintained account/pool/source assignment YAML."""

    def __init__(self, path: str):
        self.path = Path(path)

    def load(self) -> OrchestrationDocument:
        values = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        document = OrchestrationDocument.model_validate(values)
        self._validate(document)
        return document

    @staticmethod
    def _validate(document: OrchestrationDocument) -> None:
        accounts = {account.id for account in document.accounts}
        pools = {pool.id: pool for pool in document.pools}
        sources = {source.id for source in document.sources}
        if len(accounts) != len(document.accounts):
            raise ValueError("Account IDs must be unique")
        if len(pools) != len(document.pools):
            raise ValueError("Pool IDs must be unique")
        if len(sources) != len(document.sources):
            raise ValueError("Source IDs must be unique")
        for pool in document.pools:
            unknown = set(pool.account_ids) - accounts
            if unknown:
                raise ValueError(f"Pool {pool.id} references unknown accounts: {sorted(unknown)}")
        for assignment in document.assignments:
            if assignment.pool_id not in pools:
                raise ValueError(f"Assignment references unknown pool: {assignment.pool_id}")
            if assignment.account_id not in accounts:
                raise ValueError(f"Assignment references unknown account: {assignment.account_id}")
            if assignment.account_id not in pools[assignment.pool_id].account_ids:
                raise ValueError(f"Account {assignment.account_id} is not a member of pool {assignment.pool_id}")
            if assignment.source_id not in sources:
                raise ValueError(f"Assignment references unknown source: {assignment.source_id}")

    def shard_plan(self, pool_id: str, shard: int) -> list[tuple[ManagedAccount, list[Source]]]:
        document = self.load()
        accounts = {account.id: account for account in document.accounts}
        sources = {source.id: source for source in document.sources}
        pool = next((item for item in document.pools if item.id == pool_id), None)
        if pool is None:
            raise ValueError(f"Unknown pool: {pool_id}")
        grouped: dict[str, list[Source]] = defaultdict(list)
        for assignment in sorted(document.assignments, key=lambda item: item.priority):
            if assignment.pool_id == pool_id and assignment.shard == shard and assignment.enabled and not assignment.backup:
                account = accounts[assignment.account_id]
                if account.enabled:
                    grouped[account.id].append(sources[assignment.source_id])
        return [(accounts[account_id], source_list) for account_id, source_list in grouped.items()]

    def shards(self, pool_id: str) -> list[int]:
        document = self.load()
        return sorted({item.shard for item in document.assignments if item.pool_id == pool_id and item.enabled})

    def pool(self, pool_id: str) -> AccountPool:
        document = self.load()
        for pool in document.pools:
            if pool.id == pool_id:
                return pool
        raise ValueError(f"Unknown pool: {pool_id}")
