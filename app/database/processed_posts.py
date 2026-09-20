from pathlib import Path
import hashlib
import sqlite3


class ProcessedPostStore:
    def __init__(self, database_url: str):
        path = database_url.removeprefix("sqlite:///")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS processed_posts "
            "(post_id TEXT PRIMARY KEY, content_hash TEXT)"
        )
        columns = {row[1] for row in self.connection.execute("PRAGMA table_info(processed_posts)")}
        if "content_hash" not in columns:
            self.connection.execute("ALTER TABLE processed_posts ADD COLUMN content_hash TEXT")
        self.connection.execute("CREATE INDEX IF NOT EXISTS idx_processed_posts_hash ON processed_posts(content_hash)")
        self.connection.commit()

    @staticmethod
    def content_hash(content: str) -> str:
        return hashlib.sha256(" ".join(content.lower().split()).encode("utf-8")).hexdigest()

    def seen(self, post_id: str, content: str | None = None) -> bool:
        if self.connection.execute("SELECT 1 FROM processed_posts WHERE post_id = ?", (post_id,)).fetchone():
            return True
        return bool(content and self.connection.execute(
            "SELECT 1 FROM processed_posts WHERE content_hash = ?", (self.content_hash(content),)
        ).fetchone())

    def mark(self, post_id: str, content: str | None = None) -> None:
        self.connection.execute(
            "INSERT OR IGNORE INTO processed_posts(post_id, content_hash) VALUES (?, ?)",
            (post_id, self.content_hash(content) if content else None),
        )
        self.connection.commit()
