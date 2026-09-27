from app.group_discovery import FacebookGroupDiscovery, load_group_discovery


def test_group_discovery_config_and_metadata_parsing(tmp_path):
    path = tmp_path / "discovery.yaml"
    path.write_text("""group_discovery:
  queries: ["gia su"]
  account_ids: [fb_001]
  max_results_per_query: 20
""", encoding="utf-8")
    settings = load_group_discovery(str(path))
    assert settings.queries == ["gia su"]
    assert FacebookGroupDiscovery._group_url("https://www.facebook.com/groups/123/?x=1") == "https://www.facebook.com/groups/123"
    assert FacebookGroupDiscovery._members("Công khai · 1.2K thành viên") == 1200
    assert FacebookGroupDiscovery._privacy("Public · 2K members") == "PUBLIC"
