from app.orchestration.yaml_config import YamlOrchestrationConfig


def test_yaml_config_builds_account_scoped_shard_plan(tmp_path):
    path = tmp_path / "accounts.yaml"
    path.write_text(
        """accounts:
  - id: one
    facebook_uid: "1001"
    profile_path: .secrets/facebook-profiles/1001
  - id: two
    facebook_uid: "1002"
    profile_path: .secrets/facebook-profiles/1002
pools:
  - id: pilot
    account_ids: [one, two]
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
    account_id: two
    source_id: g2
    shard: 1
""",
        encoding="utf-8",
    )

    config = YamlOrchestrationConfig(str(path))
    plan = config.shard_plan("pilot", 1)

    assert [(account.id, [source.id for source in sources]) for account, sources in plan] == [("one", ["g1"]), ("two", ["g2"])]
    assert config.shards("pilot") == [1]
