"""Review, validate, and promote discovered groups into approved crawl sources."""
from pathlib import Path
import re

import yaml

from app.orchestration.yaml_config import YamlOrchestrationConfig


class GroupCandidateService:
    MAX_GROUPS_PER_SHARD = 10
    def __init__(self, store, account_pools_path: str):
        self.store, self.path = store, Path(account_pools_path)

    def candidates(self) -> list[dict]:
        return self.store.list_group_candidates()

    def validate(self, candidate: dict, account_id: str) -> str:
        document = YamlOrchestrationConfig(str(self.path)).load()
        account = next((item for item in document.accounts if item.id == account_id), None)
        if account is None:
            raise ValueError(f"Unknown account: {account_id}")
        from playwright.sync_api import sync_playwright
        profile = Path(account.profile_path)
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(str(profile), headless=True)
            page = context.new_page()
            try:
                page.goto(candidate["canonical_group_url"], wait_until="domcontentloaded", timeout=45_000)
                page.wait_for_timeout(1_500)
                blocked = any(token in page.url.lower() for token in ("/login", "/checkpoint", "/recover"))
                accessible = not blocked and (page.locator('[role="feed"]').count() > 0 or page.locator('[role="article"]').count() > 0)
                status = "ACCESSIBLE" if accessible else "NO_ACCESS"
                self.store.record_group_access(account_id, candidate["canonical_group_url"], status,
                    None if accessible else "No visible group feed/post for this account")
                return status
            finally:
                context.close()

    def approve_and_assign(self, candidate: dict, account_id: str, shard: int, pool_id: str) -> str:
        """Promote an ACCESSIBLE candidate into YAML, then central PostgreSQL."""
        if candidate.get("access_status") != "ACCESSIBLE":
            raise ValueError("Candidate must be ACCESSIBLE before approval")
        if shard < 1:
            raise ValueError("Shard must be at least 1")
        document = YamlOrchestrationConfig(str(self.path)).load()
        pool = next((item for item in document.pools if item.id == pool_id), None)
        if pool is None or account_id not in pool.account_ids:
            raise ValueError("Account must belong to the selected pool")
        approved = {"url": candidate["canonical_group_url"], "name": candidate["group_name"]}
        values = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        source_id = self._source_id(approved["url"])
        sources = values.setdefault("sources", [])
        if not any(item.get("id") == source_id for item in sources):
            sources.append({"id": source_id, "name": approved["name"], "platform": "facebook", "source_url": approved["url"], "enabled": True})
        assignments = values.setdefault("assignments", [])
        exists = any(item.get("pool_id") == pool_id and item.get("account_id") == account_id and item.get("source_id") == source_id for item in assignments)
        if not exists:
            assignments.append({"pool_id": pool_id, "account_id": account_id, "source_id": source_id,
                                "shard": shard, "priority": 100, "enabled": True, "backup": False})
        self.path.write_text(yaml.safe_dump(values, allow_unicode=True, sort_keys=False), encoding="utf-8")
        self.store.approve_group_candidate(int(candidate["candidate_id"]))
        self.store.record_group_event(int(candidate["candidate_id"]), account_id, "AUTO_ASSIGNED",
                                      f"pool={pool_id}; shard={shard}; source_id={source_id}")
        return source_id

    def validate_approve_and_assign_pending(self, account_id: str, shard: int, pool_id: str) -> dict[str, int]:
        """Process all pending candidates for an account and preserve an audit trail."""
        counts = {"approved": 0, "no_access": 0, "errors": 0, "skipped": 0}
        for candidate in self.candidates():
            if candidate["approval_status"] != "PENDING":
                continue
            try:
                status = self.validate(candidate, account_id)
                if status != "ACCESSIBLE":
                    counts["no_access"] += 1
                    continue
                candidate["access_status"] = status
                self.approve_and_assign(candidate, account_id, shard, pool_id)
                counts["approved"] += 1
            except Exception as exc:
                counts["errors"] += 1
                self.store.record_group_event(int(candidate["candidate_id"]), account_id, "AUTO_ASSIGN_ERROR",
                                              f"{type(exc).__name__}: {exc}")
        return counts

    def validate_approve_and_assign_for_pool(self, discovery_account_id: str, shard: int, pool_id: str) -> dict[str, int]:
        """Validate each discovered group against every account in one pool."""
        document = YamlOrchestrationConfig(str(self.path)).load()
        pool = next((item for item in document.pools if item.id == pool_id), None)
        if pool is None:
            raise ValueError(f"Unknown pool: {pool_id}")
        counts = {"approved_groups": 0, "assignments_added": 0, "no_access": 0, "errors": 0}
        for candidate in self.candidates():
            if candidate["approval_status"] != "PENDING":
                continue
            accessible_accounts: list[str] = []
            for account_id in pool.account_ids:
                try:
                    if self.validate(candidate, account_id) == "ACCESSIBLE":
                        accessible_accounts.append(account_id)
                except Exception as exc:
                    counts["errors"] += 1
                    self.store.record_group_event(int(candidate["candidate_id"]), account_id, "POOL_ACCESS_ERROR",
                                                  f"{type(exc).__name__}: {exc}")
            if not accessible_accounts:
                counts["no_access"] += 1
                continue
            candidate["access_status"] = "ACCESSIBLE"
            for account_id in accessible_accounts:
                try:
                    self.approve_and_assign(candidate, account_id, shard, pool_id)
                    counts["assignments_added"] += 1
                except Exception as exc:
                    counts["errors"] += 1
                    self.store.record_group_event(int(candidate["candidate_id"]), account_id, "POOL_ASSIGN_ERROR",
                                                  f"{type(exc).__name__}: {exc}")
            counts["approved_groups"] += 1
            self.store.record_group_event(int(candidate["candidate_id"]), discovery_account_id, "POOL_AUTO_APPROVED",
                                          f"pool={pool_id}; accessible_accounts={','.join(accessible_accounts)}")
        return counts

    def auto_assign_pending_for_discovery_account(self, discovery_account_id: str) -> dict[str, int]:
        """Choose the account's single pool and each target's next free shard."""
        document = YamlOrchestrationConfig(str(self.path)).load()
        pools = [pool for pool in document.pools if discovery_account_id in pool.account_ids]
        if len(pools) != 1:
            raise ValueError("Discovery account must belong to exactly one pool for automatic assignment")
        pool = pools[0]
        counts = {"approved_groups": 0, "assignments_added": 0, "no_access": 0, "errors": 0}
        for candidate in self.candidates():
            if candidate["approval_status"] != "PENDING":
                continue
            accessible_accounts: list[str] = []
            for account_id in pool.account_ids:
                try:
                    if self.validate(candidate, account_id) == "ACCESSIBLE":
                        accessible_accounts.append(account_id)
                except Exception as exc:
                    counts["errors"] += 1
                    self.store.record_group_event(int(candidate["candidate_id"]), account_id, "POOL_ACCESS_ERROR", f"{type(exc).__name__}: {exc}")
            if not accessible_accounts:
                counts["no_access"] += 1
                continue
            candidate["access_status"] = "ACCESSIBLE"
            for account_id in accessible_accounts:
                try:
                    shard = self._next_free_shard(account_id, pool.id)
                    self.approve_and_assign(candidate, account_id, shard, pool.id)
                    counts["assignments_added"] += 1
                except Exception as exc:
                    counts["errors"] += 1
                    self.store.record_group_event(int(candidate["candidate_id"]), account_id, "POOL_ASSIGN_ERROR", f"{type(exc).__name__}: {exc}")
            counts["approved_groups"] += 1
        return counts

    def reconcile_existing_sources_for_pool(self, pool_id: str, discovery_account_id: str | None = None) -> dict[str, int]:
        """Validate every currently assigned group with every account in a pool.

        A source may remain assigned to multiple accounts.  An assignment is
        removed only after a successful Facebook check returns ``NO_ACCESS``;
        transient browser errors never remove operator data.
        """
        document = YamlOrchestrationConfig(str(self.path)).load()
        pool = next((item for item in document.pools if item.id == pool_id), None)
        if pool is None:
            raise ValueError(f"Unknown pool: {pool_id}")
        source_ids = {
            item.source_id for item in document.assignments
            if item.pool_id == pool_id and item.enabled
        }
        sources = [item for item in document.sources if item.id in source_ids]
        reporter = discovery_account_id or pool.account_ids[0]
        for source in sources:
            self.store.save_group_candidate(
                url=source.source_url,
                name=source.name,
                keyword="existing_source_reconciliation",
                account_id=reporter,
            )
        candidates = {item["canonical_group_url"]: item for item in self.candidates()}
        counts = {"groups_checked": 0, "access_granted": 0, "assignments_added": 0,
                  "assignments_removed": 0, "no_access": 0, "errors": 0}
        for source in sources:
            candidate = candidates[source.source_url]
            accessible_accounts: list[str] = []
            no_access_accounts: list[str] = []
            for account_id in pool.account_ids:
                try:
                    status = self.validate(candidate, account_id)
                    if status == "ACCESSIBLE":
                        accessible_accounts.append(account_id)
                    else:
                        no_access_accounts.append(account_id)
                except Exception as exc:
                    counts["errors"] += 1
                    self.store.record_group_event(int(candidate["candidate_id"]), account_id, "RECONCILE_ACCESS_ERROR",
                                                  f"{type(exc).__name__}: {exc}")
            counts["groups_checked"] += 1
            counts["access_granted"] += len(accessible_accounts)
            counts["no_access"] += len(no_access_accounts)
            if accessible_accounts:
                candidate["access_status"] = "ACCESSIBLE"
                for account_id in accessible_accounts:
                    before = self._assignment_exists(pool_id, account_id, source.id)
                    self.approve_and_assign(candidate, account_id, self._next_free_shard(account_id, pool_id), pool_id)
                    counts["assignments_added"] += int(not before)
            for account_id in no_access_accounts:
                if self._remove_assignment(pool_id, account_id, source.id):
                    counts["assignments_removed"] += 1
        return counts

    def _assignment_exists(self, pool_id: str, account_id: str, source_id: str) -> bool:
        document = YamlOrchestrationConfig(str(self.path)).load()
        return any(item.pool_id == pool_id and item.account_id == account_id and item.source_id == source_id
                   for item in document.assignments)

    def _remove_assignment(self, pool_id: str, account_id: str, source_id: str) -> bool:
        values = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        assignments = values.get("assignments", [])
        kept = [item for item in assignments if not (
            item.get("pool_id") == pool_id and item.get("account_id") == account_id and item.get("source_id") == source_id
        )]
        if len(kept) == len(assignments):
            return False
        values["assignments"] = kept
        self.path.write_text(yaml.safe_dump(values, allow_unicode=True, sort_keys=False), encoding="utf-8")
        return True

    def _next_free_shard(self, account_id: str, pool_id: str) -> int:
        document = YamlOrchestrationConfig(str(self.path)).load()
        counts: dict[int, int] = {}
        for assignment in document.assignments:
            if assignment.pool_id == pool_id and assignment.account_id == account_id and assignment.enabled:
                counts[assignment.shard] = counts.get(assignment.shard, 0) + 1
        for shard in sorted(counts):
            if counts[shard] < self.MAX_GROUPS_PER_SHARD:
                return shard
        return max(counts, default=0) + 1

    @staticmethod
    def _source_id(url: str) -> str:
        token = url.rstrip("/").split("/")[-1]
        return "fb_group_" + re.sub(r"[^a-z0-9]+", "_", token.lower()).strip("_")
