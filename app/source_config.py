from pathlib import Path

import yaml

from app.schemas import Source


class YamlSourceService:
    """Loads explicitly allow-listed browser sources from local YAML."""
    def __init__(self, path: str):
        self.path = Path(path)

    def list_enabled(self) -> list[Source]:
        document = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        defaults = document.get("defaults", {})
        result = []
        for item in document.get("sources", []):
            values = {**defaults, **item}
            if values.get("enabled", True):
                result.append(Source(id=str(values["id"]), name=values["name"],
                    platform=values.get("platform", "facebook"), external_id=values.get("external_id"),
                    source_url=values.get("source_url")))
        return result

    def allowed_account_uids(self) -> set[str]:
        document = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        return {str(uid) for uid in document.get("defaults", {}).get("allowed_account_uids", [])}
