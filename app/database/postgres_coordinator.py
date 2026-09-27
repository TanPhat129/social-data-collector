"""PostgreSQL state for multi-account collection and Sheets outbox.

This module is intentionally separate from the legacy SQLite processed-post
store. Multi-account mode must use this central database so uniqueness and
account locks are shared by every worker.
"""
from contextlib import contextmanager
import json
from typing import Iterator

from app.orchestration.models import AccountStatus, OrchestrationDocument
from app.schemas import RawPost, TutorLead


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS crawler_accounts (
    account_id TEXT PRIMARY KEY,
    facebook_uid TEXT NOT NULL UNIQUE,
    profile_path TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('AVAILABLE','IN_USE','NEEDS_MANUAL_ACTION','DISABLED')),
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS crawler_pools (
    pool_id TEXT PRIMARY KEY,
    max_concurrent_accounts INTEGER NOT NULL CHECK (max_concurrent_accounts > 0)
);
CREATE TABLE IF NOT EXISTS crawler_sources (
    source_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    platform TEXT NOT NULL,
    source_url TEXT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE TABLE IF NOT EXISTS crawler_assignments (
    pool_id TEXT NOT NULL REFERENCES crawler_pools(pool_id) ON DELETE CASCADE,
    account_id TEXT NOT NULL REFERENCES crawler_accounts(account_id) ON DELETE CASCADE,
    source_id TEXT NOT NULL REFERENCES crawler_sources(source_id) ON DELETE CASCADE,
    shard INTEGER NOT NULL CHECK (shard > 0),
    priority INTEGER NOT NULL DEFAULT 100,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    backup BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (pool_id, account_id, source_id)
);
CREATE TABLE IF NOT EXISTS crawl_rounds (
    round_id UUID PRIMARY KEY,
    pool_id TEXT NOT NULL REFERENCES crawler_pools(pool_id),
    shard INTEGER NOT NULL,
    status TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS crawled_posts (
    post_id BIGSERIAL PRIMARY KEY,
    platform TEXT NOT NULL,
    canonical_post_url TEXT NOT NULL,
    source_id TEXT NOT NULL REFERENCES crawler_sources(source_id),
    content_hash TEXT NOT NULL,
    raw_content TEXT NOT NULL,
    posted_at TIMESTAMPTZ,
    collected_at TIMESTAMPTZ NOT NULL,
    author_url TEXT,
    first_account_id TEXT REFERENCES crawler_accounts(account_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (platform, canonical_post_url)
);
CREATE TABLE IF NOT EXISTS leads (
    lead_id BIGSERIAL PRIMARY KEY,
    post_id BIGINT NOT NULL UNIQUE REFERENCES crawled_posts(post_id),
    payload JSONB NOT NULL,
    confidence DOUBLE PRECISION NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS sheet_outbox (
    outbox_id BIGSERIAL PRIMARY KEY,
    lead_id BIGINT NOT NULL UNIQUE REFERENCES leads(lead_id),
    status TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING','IN_PROGRESS','EXPORTED','RETRY','FAILED')),
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    exported_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_sheet_outbox_pending ON sheet_outbox(status, outbox_id);
CREATE TABLE IF NOT EXISTS group_candidates (
    candidate_id BIGSERIAL PRIMARY KEY,
    canonical_group_url TEXT NOT NULL UNIQUE,
    group_name TEXT NOT NULL,
    privacy TEXT,
    member_count BIGINT,
    post_frequency TEXT,
    discovery_keyword TEXT NOT NULL,
    discovered_by_account_id TEXT REFERENCES crawler_accounts(account_id),
    access_status TEXT NOT NULL DEFAULT 'UNKNOWN' CHECK (access_status IN ('UNKNOWN','ACCESSIBLE','NO_ACCESS','ERROR')),
    approval_status TEXT NOT NULL DEFAULT 'PENDING' CHECK (approval_status IN ('PENDING','APPROVED','REJECTED')),
    discovered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    validated_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS group_access (
    account_id TEXT NOT NULL REFERENCES crawler_accounts(account_id) ON DELETE CASCADE,
    candidate_id BIGINT NOT NULL REFERENCES group_candidates(candidate_id) ON DELETE CASCADE,
    status TEXT NOT NULL CHECK (status IN ('ACCESSIBLE','NO_ACCESS','ERROR')),
    checked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    detail TEXT,
    PRIMARY KEY (account_id, candidate_id)
);
CREATE TABLE IF NOT EXISTS group_candidate_events (
    event_id BIGSERIAL PRIMARY KEY,
    candidate_id BIGINT REFERENCES group_candidates(candidate_id) ON DELETE SET NULL,
    account_id TEXT REFERENCES crawler_accounts(account_id) ON DELETE SET NULL,
    action TEXT NOT NULL,
    detail TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_group_candidate_events_candidate ON group_candidate_events(candidate_id, event_id);
"""


class PostgresCoordinator:
    def __init__(self, dsn: str):
        if not dsn.startswith(("postgres://", "postgresql://")):
            raise ValueError("POSTGRES_DSN must be a PostgreSQL DSN")
        self.dsn = dsn

    @contextmanager
    def _connection(self) -> Iterator:
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError("Install PostgreSQL support: pip install -r requirements.txt") from exc
        with psycopg.connect(self.dsn) as connection:
            yield connection

    def initialize_schema(self) -> None:
        with self._connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(SCHEMA_SQL)

    def sync_yaml(self, document: OrchestrationDocument) -> None:
        """Upsert static YAML configuration without overwriting live statuses."""
        with self._connection() as connection:
            with connection.cursor() as cursor:
                for account in document.accounts:
                    cursor.execute(
                        """INSERT INTO crawler_accounts(account_id, facebook_uid, profile_path, status, enabled)
                        VALUES (%s,%s,%s,%s,%s)
                        ON CONFLICT (account_id) DO UPDATE SET facebook_uid=EXCLUDED.facebook_uid,
                        profile_path=EXCLUDED.profile_path, enabled=EXCLUDED.enabled, updated_at=NOW()""",
                        (account.id, account.facebook_uid, account.profile_path, account.status.value, account.enabled),
                    )
                for pool in document.pools:
                    cursor.execute(
                        """INSERT INTO crawler_pools(pool_id, max_concurrent_accounts) VALUES (%s,%s)
                        ON CONFLICT (pool_id) DO UPDATE SET max_concurrent_accounts=EXCLUDED.max_concurrent_accounts""",
                        (pool.id, pool.max_concurrent_accounts),
                    )
                for source in document.sources:
                    cursor.execute(
                        """INSERT INTO crawler_sources(source_id,name,platform,source_url,enabled) VALUES (%s,%s,%s,%s,%s)
                        ON CONFLICT (source_id) DO UPDATE SET name=EXCLUDED.name, platform=EXCLUDED.platform,
                        source_url=EXCLUDED.source_url, enabled=EXCLUDED.enabled""",
                        (source.id, source.name, source.platform, source.source_url, source.enabled),
                    )
                for assignment in document.assignments:
                    cursor.execute(
                        """INSERT INTO crawler_assignments(pool_id,account_id,source_id,shard,priority,enabled,backup)
                        VALUES (%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (pool_id,account_id,source_id) DO UPDATE SET shard=EXCLUDED.shard,
                        priority=EXCLUDED.priority, enabled=EXCLUDED.enabled, backup=EXCLUDED.backup""",
                        (assignment.pool_id, assignment.account_id, assignment.source_id, assignment.shard,
                         assignment.priority, assignment.enabled, assignment.backup),
                    )

    def register_runtime_sources(self, sources) -> None:
        """Register temporary Search sources without turning them into assignments."""
        with self._connection() as connection:
            with connection.cursor() as cursor:
                for source in sources:
                    cursor.execute(
                        """INSERT INTO crawler_sources(source_id,name,platform,source_url,enabled) VALUES (%s,%s,%s,%s,%s)
                        ON CONFLICT (source_id) DO UPDATE SET name=EXCLUDED.name, source_url=EXCLUDED.source_url, enabled=EXCLUDED.enabled""",
                        (source.id, source.name, source.platform, source.source_url, source.enabled),
                    )

    def acquire_account(self, account_id: str) -> bool:
        with self._connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """UPDATE crawler_accounts SET status='IN_USE', updated_at=NOW()
                    WHERE account_id=%s AND enabled=TRUE AND status='AVAILABLE'""", (account_id,)
                )
                return cursor.rowcount == 1

    def release_account(self, account_id: str, status: AccountStatus = AccountStatus.AVAILABLE) -> None:
        if status == AccountStatus.IN_USE:
            raise ValueError("An account cannot be released as IN_USE")
        with self._connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("UPDATE crawler_accounts SET status=%s, updated_at=NOW() WHERE account_id=%s", (status.value, account_id))

    def list_account_states(self) -> list[dict]:
        with self._connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT account_id, facebook_uid, status, enabled, updated_at FROM crawler_accounts ORDER BY account_id")
                columns = [item.name for item in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def group_access_summary(self, account_id: str) -> list[dict]:
        """Count discovery access checks for one account without exposing group data."""
        with self._connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT status, COUNT(*) AS groups
                    FROM group_access WHERE account_id=%s GROUP BY status ORDER BY status""",
                    (account_id,),
                )
                columns = [item.name for item in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def recover_in_use_accounts(self) -> int:
        """Explicit operator recovery; call only after all workers are stopped."""
        with self._connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""UPDATE crawler_accounts SET status='AVAILABLE', updated_at=NOW()
                               WHERE status='IN_USE' AND enabled=TRUE""")
                return cursor.rowcount

    def claim_post(self, post: RawPost, account_id: str, content_hash: str) -> bool:
        """Atomically claim one canonical post across every account."""
        if not post.post_url:
            return False
        with self._connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO crawled_posts(platform,canonical_post_url,source_id,content_hash,raw_content,posted_at,collected_at,author_url,first_account_id)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (platform,canonical_post_url) DO NOTHING""",
                    (post.source.platform, post.post_url, post.source.id, content_hash, post.content, post.posted_at,
                     post.collected_at, post.author_url, account_id),
                )
                return cursor.rowcount == 1

    def create_lead_and_outbox(self, lead: TutorLead) -> None:
        """Insert lead and one Sheets outbox record in a single transaction."""
        if not lead.post_url:
            raise ValueError("Lead post_url is required")
        payload = lead.model_dump(mode="json")
        with self._connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT post_id FROM crawled_posts WHERE platform=%s AND canonical_post_url=%s", (lead.platform, lead.post_url))
                row = cursor.fetchone()
                if row is None:
                    raise RuntimeError("Post must be claimed before creating a lead")
                cursor.execute(
                    """INSERT INTO leads(post_id,payload,confidence) VALUES (%s,%s::jsonb,%s)
                    ON CONFLICT (post_id) DO NOTHING RETURNING lead_id""",
                    (row[0], json.dumps(payload), lead.confidence),
                )
                created = cursor.fetchone()
                if created:
                    cursor.execute("INSERT INTO sheet_outbox(lead_id) VALUES (%s)", (created[0],))

    def claim_sheet_outbox(self, limit: int) -> list[tuple[int, TutorLead]]:
        """Lease pending rows to the single Sheets writer.

        ``FOR UPDATE SKIP LOCKED`` also makes this safe should an operator
        accidentally start a second writer: a row can be leased by one writer
        only.  The normal deployment still runs exactly one writer.
        """
        with self._connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """WITH selected AS (
                        SELECT outbox_id FROM sheet_outbox
                        WHERE status IN ('PENDING', 'RETRY')
                        ORDER BY outbox_id
                        FOR UPDATE SKIP LOCKED
                        LIMIT %s
                    )
                    UPDATE sheet_outbox o SET status='IN_PROGRESS', attempts=o.attempts + 1
                    FROM selected WHERE o.outbox_id=selected.outbox_id
                    RETURNING o.outbox_id, (SELECT payload FROM leads WHERE lead_id=o.lead_id)""",
                    (limit,),
                )
                return [(row[0], TutorLead.model_validate(row[1])) for row in cursor.fetchall()]

    def mark_sheet_exported(self, outbox_ids: list[int]) -> None:
        if not outbox_ids:
            return
        with self._connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""UPDATE sheet_outbox SET status='EXPORTED', exported_at=NOW(), last_error=NULL
                               WHERE outbox_id = ANY(%s)""", (outbox_ids,))

    def mark_sheet_retry(self, outbox_ids: list[int], error: str) -> None:
        if not outbox_ids:
            return
        with self._connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""UPDATE sheet_outbox SET status='RETRY', last_error=%s
                               WHERE outbox_id = ANY(%s)""", (error[:1_000], outbox_ids))

    def save_group_candidate(self, *, url: str, name: str, keyword: str, account_id: str,
                             privacy: str | None = None, member_count: int | None = None,
                             post_frequency: str | None = None) -> bool:
        """Insert a discovery result once; discovery never enables crawling."""
        with self._connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO group_candidates(canonical_group_url,group_name,privacy,member_count,post_frequency,discovery_keyword,discovered_by_account_id)
                    VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (canonical_group_url) DO NOTHING""",
                    (url, name, privacy, member_count, post_frequency, keyword, account_id),
                )
                return cursor.rowcount == 1

    def record_group_access(self, account_id: str, group_url: str, status: str, detail: str | None = None) -> None:
        if status not in {"ACCESSIBLE", "NO_ACCESS", "ERROR"}:
            raise ValueError("Invalid group access status")
        with self._connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT candidate_id FROM group_candidates WHERE canonical_group_url=%s", (group_url,))
                row = cursor.fetchone()
                if row is None:
                    raise ValueError("Unknown group candidate")
                cursor.execute(
                    """INSERT INTO group_access(account_id,candidate_id,status,detail) VALUES (%s,%s,%s,%s)
                    ON CONFLICT (account_id,candidate_id) DO UPDATE SET status=EXCLUDED.status, detail=EXCLUDED.detail, checked_at=NOW()""",
                    (account_id, row[0], status, detail),
                )
                # Candidate is globally ACCESSIBLE if at least one account can
                # see it. Per-account truth remains in group_access.
                cursor.execute("SELECT EXISTS(SELECT 1 FROM group_access WHERE candidate_id=%s AND status='ACCESSIBLE')", (row[0],))
                accessible_anywhere = cursor.fetchone()[0]
                aggregate = "ACCESSIBLE" if accessible_anywhere else status
                cursor.execute("UPDATE group_candidates SET access_status=%s, validated_at=NOW() WHERE candidate_id=%s", (aggregate, row[0]))
                cursor.execute("INSERT INTO group_candidate_events(candidate_id,account_id,action,detail) VALUES (%s,%s,%s,%s)",
                               (row[0], account_id, f"ACCESS_{status}", detail))

    def list_group_candidates(self) -> list[dict]:
        with self._connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""SELECT candidate_id, canonical_group_url, group_name, privacy, member_count,
                               post_frequency, discovery_keyword, access_status, approval_status
                               FROM group_candidates ORDER BY candidate_id""")
                columns = [item.name for item in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def approve_group_candidate(self, candidate_id: int) -> dict:
        with self._connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""UPDATE group_candidates SET approval_status='APPROVED'
                               WHERE candidate_id=%s AND access_status='ACCESSIBLE'
                               RETURNING canonical_group_url, group_name""", (candidate_id,))
                row = cursor.fetchone()
                if row is None:
                    raise ValueError("Candidate must be ACCESSIBLE before approval")
                return {"url": row[0], "name": row[1]}

    def record_group_event(self, candidate_id: int, account_id: str, action: str, detail: str | None = None) -> None:
        with self._connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("INSERT INTO group_candidate_events(candidate_id,account_id,action,detail) VALUES (%s,%s,%s,%s)",
                               (candidate_id, account_id, action, detail))
