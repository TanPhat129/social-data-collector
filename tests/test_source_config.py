from app.source_config import YamlSourceService


def test_yaml_source_service_loads_allowlisted_sources(tmp_path):
    path = tmp_path / "sources.yaml"
    path.write_text("""defaults:\n  platform: facebook\n  enabled: true\nsources:\n  - id: one\n    name: Test group\n    source_url: https://www.facebook.com/groups/one\n  - id: disabled\n    name: Disabled\n    enabled: false\n""", encoding="utf-8")

    sources = YamlSourceService(str(path)).list_enabled()

    assert len(sources) == 1
    assert sources[0].source_url == "https://www.facebook.com/groups/one"
