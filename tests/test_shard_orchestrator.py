from app.orchestration.models import AccountStatus, ManagedAccount
from app.orchestration.orchestrator import ShardOrchestrator, ShardOutcome
from app.orchestration.yaml_config import YamlOrchestrationConfig
from app.schemas import Source


class StateStore:
    def __init__(self):
        self.available = {"one", "two"}
        self.released = []

    def acquire_account(self, account_id):
        if account_id not in self.available:
            return False
        self.available.remove(account_id)
        return True

    def release_account(self, account_id, status=AccountStatus.AVAILABLE):
        self.released.append((account_id, status))
        if status == AccountStatus.AVAILABLE:
            self.available.add(account_id)


class Worker:
    def run(self, account: ManagedAccount, sources, timeout_seconds):
        return len(sources)


def test_orchestrator_waits_each_shard_before_next(tmp_path):
    path = tmp_path / "accounts.yaml"
    path.write_text(
        """shard_pause_seconds: 30
accounts:
  - id: one
    facebook_uid: "1001"
    profile_path: .secrets/facebook-profiles/1001
pools:
  - id: pilot
    account_ids: [one]
sources:
  - id: g1
    name: Group 1
    source_url: https://www.facebook.com/groups/g1
  - id: g2
    name: Group 2
    source_url: https://www.facebook.com/groups/g2
assignments:
  - pool_id: pilot
    account_id: one
    source_id: g1
    shard: 1
  - pool_id: pilot
    account_id: one
    source_id: g2
    shard: 2
""",
        encoding="utf-8",
    )
    states = StateStore()
    orchestrator = ShardOrchestrator(YamlOrchestrationConfig(str(path)), states, Worker())

    results = orchestrator.run_round("pilot", pause_seconds=0)

    assert [result.outcome for result in results] == [ShardOutcome.COMPLETED, ShardOutcome.COMPLETED]
    assert [result.accepted_leads for result in results] == [1, 1]
    assert states.released == [("one", AccountStatus.AVAILABLE), ("one", AccountStatus.AVAILABLE)]


def test_orchestrator_calls_export_hook_after_each_shard(tmp_path):
    path = tmp_path / "accounts.yaml"
    path.write_text("""accounts:
  - {id: one, facebook_uid: "1001", profile_path: .secrets/facebook-profiles/1001}
pools:
  - {id: pilot, account_ids: [one]}
sources:
  - {id: g1, name: Group 1, source_url: https://www.facebook.com/groups/g1}
  - {id: g2, name: Group 2, source_url: https://www.facebook.com/groups/g2}
assignments:
  - {pool_id: pilot, account_id: one, source_id: g1, shard: 1}
  - {pool_id: pilot, account_id: one, source_id: g2, shard: 2}
""", encoding="utf-8")
    hooks = []
    ShardOrchestrator(YamlOrchestrationConfig(str(path)), StateStore(), Worker()).run_round(
        "pilot", pause_seconds=0, after_shard=hooks.append)
    assert hooks == [1, 2]


def test_orchestrator_can_smoke_test_one_shard_and_one_source(tmp_path):
    path = tmp_path / "accounts.yaml"
    path.write_text(
        """accounts:
  - {id: one, facebook_uid: "1001", profile_path: .secrets/facebook-profiles/1001}
pools:
  - {id: pilot, account_ids: [one]}
sources:
  - {id: g1, name: Group 1, source_url: https://www.facebook.com/groups/g1}
  - {id: g2, name: Group 2, source_url: https://www.facebook.com/groups/g2}
assignments:
  - {pool_id: pilot, account_id: one, source_id: g1, shard: 1}
  - {pool_id: pilot, account_id: one, source_id: g2, shard: 1}
""", encoding="utf-8")
    result = ShardOrchestrator(YamlOrchestrationConfig(str(path)), StateStore(), Worker()).run_round(
        "pilot", only_shard=1, max_sources_per_account=1)
    assert len(result) == 1
    assert result[0].sources == 1


def test_smoke_limit_distributes_sources_across_accounts():
    accounts = [ManagedAccount(id=f"a{number}", facebook_uid=str(1000 + number), profile_path=f".secrets/{1000 + number}") for number in (1, 2)]
    plan = [(account, [Source(id=f"{account.id}_{n}", name=str(n), source_url="https://www.facebook.com/groups/x") for n in range(4)]) for account in accounts]
    limited = ShardOrchestrator._limit_sources_total(plan, 5)
    assert [len(sources) for _, sources in limited] == [3, 2]
