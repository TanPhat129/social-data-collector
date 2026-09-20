from pathlib import Path
import yaml


class KeywordFilter:
    def __init__(self, keywords: list[str]):
        self.keywords = [word.lower().strip() for word in keywords]

    @classmethod
    def from_yaml(cls, path: str) -> "KeywordFilter":
        return cls((yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}).get("keywords", []))

    def matches(self, content: str) -> bool:
        return any(word in content.lower() for word in self.keywords)

