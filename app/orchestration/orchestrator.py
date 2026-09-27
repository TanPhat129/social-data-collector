"""Barrier-based shard orchestration for one configured account pool."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from enum import StrEnum
import logging
from time import sleep
from typing import Callable, Protocol
from uuid import uuid4

from app.orchestration.models import AccountStatus, ManagedAccount
from app.orchestration.yaml_config import YamlOrchestrationConfig
from app.schemas import Source

logger = logging.getLogger(__name__)


class ShardOutcome(StrEnum):
    COMPLETED = "COMPLETED"
    TIMEOUT = "TIMEOUT"
    FAILED = "FAILED"
    NEEDS_MANUAL_ACTION = "NEEDS_MANUAL_ACTION"
    SKIPPED = "SKIPPED"


@dataclass(frozen=True)
class AccountShardResult:
    account_id: str
    outcome: ShardOutcome
    sources: int
    accepted_leads: int = 0


class AccountStateStore(Protocol):
    def acquire_account(self, account_id: str) -> bool: ...
    def release_account(self, account_id: str, status: AccountStatus = AccountStatus.AVAILABLE) -> None: ...


class AccountShardWorker(Protocol):
    def run(self, account: ManagedAccount, sources: list[Source], timeout_seconds: int) -> int: ...


class ShardOrchestrator:
    """Runs a shard barrier: all selected account workers finish before next shard."""

    def __init__(self, config: YamlOrchestrationConfig, states: AccountStateStore, worker: AccountShardWorker):
        self.config, self.states, self.worker = config, states, worker

    def run_round(self, pool_id: str, *, pause_seconds: int | None = None,
                  only_shard: int | None = None, max_sources_per_account: int | None = None,
                  max_sources_total: int | None = None,
                  after_shard: Callable[[int], None] | None = None) -> list[AccountShardResult]:
        document = self.config.load()
        pool = self.config.pool(pool_id)
        pause = pause_seconds if pause_seconds is not None else document.shard_pause_seconds
        results: list[AccountShardResult] = []
        round_id = uuid4()
        logger.info("crawl_round=%s pool=%s started", round_id, pool_id)
        shards = self.config.shards(pool_id)
        if only_shard is not None:
            if only_shard not in shards:
                raise ValueError(f"Shard {only_shard} does not exist in pool {pool_id}")
            shards = [only_shard]
        for position, shard in enumerate(shards):
            plan = self.config.shard_plan(pool_id, shard)
            if max_sources_per_account is not None:
                if max_sources_per_account < 1:
                    raise ValueError("max_sources_per_account must be at least 1")
                plan = [(account, sources[:max_sources_per_account]) for account, sources in plan]
            if max_sources_total is not None:
                if max_sources_total < 1:
                    raise ValueError("max_sources_total must be at least 1")
                plan = self._limit_sources_total(plan, max_sources_total)
            shard_results = self._run_shard(plan, pool.max_concurrent_accounts, document.account_shard_timeout_seconds)
            results.extend(shard_results)
            logger.info("crawl_round=%s pool=%s shard=%s finished results=%s", round_id, pool_id, shard,
                        {result.outcome: sum(item.outcome == result.outcome for item in shard_results) for result in shard_results})
            if after_shard is not None:
                after_shard(shard)
            if position + 1 < len(shards):
                sleep(pause)
        logger.info("crawl_round=%s pool=%s finished", round_id, pool_id)
        return results

    @staticmethod
    def _limit_sources_total(plan: list[tuple[ManagedAccount, list[Source]]], limit: int) -> list[tuple[ManagedAccount, list[Source]]]:
        """Take a small smoke-test sample fairly: round-robin across accounts."""
        selected = [(account, []) for account, _ in plan]
        positions = [0] * len(plan)
        while sum(len(sources) for _, sources in selected) < limit:
            progressed = False
            for index, (_, sources) in enumerate(plan):
                if positions[index] >= len(sources) or sum(len(items) for _, items in selected) >= limit:
                    continue
                selected[index][1].append(sources[positions[index]])
                positions[index] += 1
                progressed = True
            if not progressed:
                break
        return [(account, sources) for account, sources in selected if sources]

    def _run_shard(self, plan: list[tuple[ManagedAccount, list[Source]]], max_workers: int, timeout_seconds: int) -> list[AccountShardResult]:
        selected: list[tuple[ManagedAccount, list[Source]]] = []
        results: list[AccountShardResult] = []
        for account, sources in plan:
            if account.status != AccountStatus.AVAILABLE:
                logger.warning("account=%s shard skipped: configured_status=%s", account.id, account.status)
                results.append(AccountShardResult(account.id, ShardOutcome.SKIPPED, len(sources)))
                continue
            if not self.states.acquire_account(account.id):
                logger.warning("account=%s shard skipped: database_status is not AVAILABLE; inspect account status after all workers stop", account.id)
                results.append(AccountShardResult(account.id, ShardOutcome.SKIPPED, len(sources)))
                continue
            selected.append((account, sources))
        with ThreadPoolExecutor(max_workers=min(max_workers, len(selected) or 1), thread_name_prefix="facebook-account") as executor:
            futures = {executor.submit(self._run_account, account, sources, timeout_seconds): (account, sources)
                       for account, sources in selected}
            for future in as_completed(futures):
                account, sources = futures[future]
                try:
                    results.append(future.result())
                except Exception:
                    logger.exception("account=%s shard failed", account.id)
                    self.states.release_account(account.id, AccountStatus.NEEDS_MANUAL_ACTION)
                    results.append(AccountShardResult(account.id, ShardOutcome.FAILED, len(sources)))
        return results

    def _run_account(self, account: ManagedAccount, sources: list[Source], timeout_seconds: int) -> AccountShardResult:
        try:
            accepted = self.worker.run(account, sources, timeout_seconds)
        except TimeoutError:
            self.states.release_account(account.id, AccountStatus.AVAILABLE)
            return AccountShardResult(account.id, ShardOutcome.TIMEOUT, len(sources))
        except PermissionError:
            self.states.release_account(account.id, AccountStatus.NEEDS_MANUAL_ACTION)
            return AccountShardResult(account.id, ShardOutcome.NEEDS_MANUAL_ACTION, len(sources))
        except Exception:
            self.states.release_account(account.id, AccountStatus.NEEDS_MANUAL_ACTION)
            raise
        self.states.release_account(account.id, AccountStatus.AVAILABLE)
        return AccountShardResult(account.id, ShardOutcome.COMPLETED, len(sources), accepted)
