"""One central crawl round followed by sequential Google Sheets export."""
import logging
from time import sleep
from typing import Callable

from app.orchestration.orchestrator import ShardOrchestrator
from app.orchestration.workers import GoogleSheetsOutboxWorker

logger = logging.getLogger(__name__)


class CentralCrawlRuntime:
    def __init__(self, orchestrator: ShardOrchestrator, sheet_writer: GoogleSheetsOutboxWorker):
        self.orchestrator, self.sheet_writer = orchestrator, sheet_writer

    def run_round(self, pool_id: str, *, only_shard: int | None = None,
                  max_sources_per_account: int | None = None, max_sources_total: int | None = None) -> tuple[int, int]:
        try:
            results = self.orchestrator.run_round(pool_id, only_shard=only_shard,
                                                  max_sources_per_account=max_sources_per_account,
                                                  max_sources_total=max_sources_total,
                                                  after_shard=self._flush_after_shard)
        except KeyboardInterrupt:
            exported = self.flush_pending()
            logger.info("graceful_stop=true sheet_exported=%d", exported)
            raise
        accepted = sum(result.accepted_leads for result in results)
        exported = self.flush_pending()
        logger.info("pool=%s accepted_leads=%d sheet_exported=%d", pool_id, accepted, exported)
        return accepted, exported

    def flush_pending(self) -> int:
        """Export committed leads before normal completion or a Ctrl+C stop."""
        exported = 0
        while True:
            count = self.sheet_writer.flush_once()
            if not count:
                break
            exported += count
        return exported

    def _flush_after_shard(self, shard: int) -> None:
        try:
            exported = self.flush_pending()
            logger.info("shard=%s sheet_exported=%d before_pause=true", shard, exported)
        except Exception:
            # Outbox rows are marked RETRY by the writer and can be retried by
            # the next shard or the next run without interrupting collection.
            logger.exception("shard=%s sheet_export_failed_before_pause", shard)

    def run_continuously(self, pool_ids: list[str], *, sleep_func: Callable[[float], None] = sleep,
                         max_rounds: int | None = None) -> None:
        """Run full rounds forever; each round already flushes after every shard."""
        pause = self.orchestrator.config.load().shard_pause_seconds
        completed = 0
        while max_rounds is None or completed < max_rounds:
            for pool_id in pool_ids:
                self.run_round(pool_id)
            completed += 1
            if max_rounds is None or completed < max_rounds:
                logger.info("continuous_round=%d completed; waiting=%ss before shard 1", completed, pause)
                sleep_func(pause)
