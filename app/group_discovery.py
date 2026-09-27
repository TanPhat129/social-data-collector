"""Discover group candidates without adding them to the crawl schedule."""
from pathlib import Path
import re
from urllib.parse import quote, urlparse

import yaml
from pydantic import BaseModel, Field

from app.orchestration.models import ManagedAccount


class GroupDiscoverySettings(BaseModel):
    enabled: bool = True
    queries: list[str] = Field(min_length=1)
    max_results_per_query: int = Field(default=30, ge=1, le=100)
    account_ids: list[str] = Field(min_length=1)


def load_group_discovery(path: str) -> GroupDiscoverySettings:
    values = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return GroupDiscoverySettings.model_validate(values.get("group_discovery", values))


class FacebookGroupDiscovery:
    """Reads only group search results visible to the supplied logged-in account."""
    def discover(self, account: ManagedAccount, settings: GroupDiscoverySettings) -> list[dict]:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError("Install Playwright before group discovery") from exc
        profile = Path(account.profile_path)
        if profile.name != account.facebook_uid:
            raise ValueError("profile_path must end with the account Facebook UID")
        candidates: dict[str, dict] = {}
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(str(profile), headless=True)
            page = context.new_page()
            try:
                for keyword in settings.queries:
                    page.goto(f"https://www.facebook.com/search/groups/?q={quote(keyword)}", wait_until="domcontentloaded", timeout=45_000)
                    page.wait_for_timeout(2_000)
                    for _ in range(2):
                        page.mouse.wheel(0, 1_200)
                        page.wait_for_timeout(600)
                    links = page.locator('a[href*="/groups/"]').evaluate_all("nodes => nodes.map(n => ({href:n.href,text:(n.innerText||'').trim(),parent:(n.parentElement?.parentElement?.innerText||'').trim()}))")
                    for item in links:
                        url = self._group_url(item["href"])
                        if not url or url in candidates or not item["text"]:
                            continue
                        meta = item["parent"]
                        candidates[url] = {"url": url, "name": item["text"], "keyword": keyword,
                                           "privacy": self._privacy(meta), "member_count": self._members(meta),
                                           "post_frequency": self._frequency(meta)}
                        if len(candidates) >= settings.max_results_per_query * len(settings.queries):
                            break
            finally:
                context.close()
        return list(candidates.values())

    @staticmethod
    def _group_url(url: str) -> str | None:
        parsed = urlparse(url)
        if parsed.netloc.lower() not in {"facebook.com", "www.facebook.com"}:
            return None
        match = re.match(r"/groups/([^/?#]+)", parsed.path)
        return f"https://www.facebook.com/groups/{match.group(1)}" if match else None

    @staticmethod
    def _privacy(text: str) -> str | None:
        lowered = text.lower()
        return "PUBLIC" if "công khai" in lowered or "public" in lowered else "PRIVATE" if "riêng tư" in lowered or "private" in lowered else None

    @staticmethod
    def _members(text: str) -> int | None:
        match = re.search(r"(\d+(?:[.,]\d+)?)\s*([km])?\s*(?:thành viên|members)", text, re.I)
        if not match: return None
        amount = float(match.group(1).replace(",", ".")); unit = (match.group(2) or "").lower()
        return int(amount * (1_000_000 if unit == "m" else 1_000 if unit == "k" else 1))

    @staticmethod
    def _frequency(text: str) -> str | None:
        match = re.search(r"\d+\+?\s*(?:bài viết\s*(?:mỗi|/)?\s*(?:ngày|tuần)|posts?\s+a\s+(?:day|week))", text, re.I)
        return match.group(0) if match else None
