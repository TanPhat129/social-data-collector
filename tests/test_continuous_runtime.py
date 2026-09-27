from app.orchestration.runtime import CentralCrawlRuntime


class Config:
    def load(self):
        return type("Document", (), {"shard_pause_seconds": 30})()


class Orchestrator:
    config = Config()


class Runtime(CentralCrawlRuntime):
    def __init__(self):
        self.orchestrator = Orchestrator()
        self.sheet_writer = None
        self.rounds = []

    def run_round(self, pool_id, **kwargs):
        self.rounds.append(pool_id)
        return 0, 0


def test_continuous_runtime_restarts_at_first_pool_after_each_round():
    runtime = Runtime()
    waits = []
    runtime.run_continuously(["one", "two"], sleep_func=waits.append, max_rounds=2)
    assert runtime.rounds == ["one", "two", "one", "two"]
    assert waits == [30]
