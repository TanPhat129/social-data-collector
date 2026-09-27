import pytest

from app.orchestration.runtime import CentralCrawlRuntime


class InterruptedOrchestrator:
    def run_round(self, *args, **kwargs):
        raise KeyboardInterrupt


class Outbox:
    def __init__(self): self.calls = 0
    def flush_once(self):
        self.calls += 1
        return 1 if self.calls == 1 else 0


def test_ctrl_c_flushes_committed_outbox_leads():
    outbox = Outbox()
    with pytest.raises(KeyboardInterrupt):
        CentralCrawlRuntime(InterruptedOrchestrator(), outbox).run_round("pilot")
    assert outbox.calls == 2
