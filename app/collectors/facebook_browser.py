"""Playwright connector for Facebook sources visible to an authorized session.

It deliberately does not automate login, solve challenges, or evade platform
controls. Create the persistent profile interactively outside this application.
"""
from datetime import datetime
import hashlib
import logging
from pathlib import Path
from urllib.parse import urlparse

from app.collectors.base import BaseCollector
from app.schemas import RawPost, Source

logger = logging.getLogger(__name__)


class FacebookBrowserCollector(BaseCollector):
    POST_MESSAGE_SELECTORS = (
        '[data-ad-comet-preview="message"]',
        '[data-ad-preview="message"]',
        '[data-ad-rendering-role="story_message"]',
        '[data-testid="post_message"]',
    )
    def __init__(self, profile_root: str, account_uid: str, *, headless: bool = True, max_posts: int = 30, max_scrolls: int = 2,
                 allowed_account_uids: set[str] | None = None):
        if not account_uid or not account_uid.isdecimal():
            raise ValueError("FACEBOOK_BROWSER_ACCOUNT_UID must be a numeric Facebook UID")
        if not profile_root:
            raise ValueError("FACEBOOK_BROWSER_PROFILE_ROOT is required for the browser connector")
        self.profile_path = str(Path(profile_root) / account_uid)
        self.account_uid = account_uid
        self.headless, self.max_posts, self.max_scrolls = headless, max_posts, max_scrolls
        self.allowed_account_uids = allowed_account_uids or set()

    def _validate_session_account(self, context) -> None:
        uid = next((str(cookie["value"]) for cookie in context.cookies("https://www.facebook.com") if cookie.get("name") == "c_user"), None)
        if uid != self.account_uid:
            raise RuntimeError("The browser profile is not logged in as FACEBOOK_BROWSER_ACCOUNT_UID")
        if self.allowed_account_uids and uid not in self.allowed_account_uids:
            raise RuntimeError("The browser profile UID is not in sources.yaml allowed_account_uids")

    @staticmethod
    def _validate_url(url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.netloc.lower() not in {"facebook.com", "www.facebook.com", "m.facebook.com"}:
            raise ValueError("Browser sources must use an https://facebook.com URL")

    @staticmethod
    def _post_id(url: str | None, content: str) -> str:
        seed = url or content
        return f"browser-{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:24]}"

    def collect(self, source: Source) -> list[RawPost]:
        if source.platform.lower() != "facebook":
            return []
        if not source.source_url:
            raise ValueError(f"Source {source.id} has no source_url")
        self._validate_url(source.source_url)
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError("Install Playwright first: pip install -r requirements.txt && python -m playwright install chromium") from exc

        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(self.profile_path, headless=self.headless)
            page = context.new_page()
            try:
                page.goto(source.source_url, wait_until="domcontentloaded", timeout=45_000)
                self._validate_session_account(context)
                if any(token in page.url.lower() for token in ("/login", "/checkpoint", "/recover")):
                    raise RuntimeError("Facebook session requires interactive login or checkpoint review")
                # Facebook renders the feed after DOMContentLoaded. Capture the
                # initial viewport before scrolling because its virtualized DOM
                # can unmount story bodies once comments enter the viewport.
                page.wait_for_timeout(2_500)
                posts_by_id = {post.post_id: post for post in self._extract(page, source)}
                article_counts = [page.locator('[role="article"]').count()]
                feed_card_counts = [page.locator('[role="feed"] > div').count()]
                for _ in range(self.max_scrolls):
                    page.mouse.wheel(0, 1_200)
                    page.wait_for_timeout(800)
                    article_counts.append(page.locator('[role="article"]').count())
                    feed_card_counts.append(page.locator('[role="feed"] > div').count())
                    for post in self._extract(page, source):
                        posts_by_id.setdefault(post.post_id, post)
                posts = list(posts_by_id.values())
                logger.debug("source=%s url=%s article_counts=%s feed_card_counts=%s extracted_posts=%d", source.id,
                    page.url, article_counts, feed_card_counts, len(posts))
                return posts
            finally:
                context.close()

    def _extract(self, page, source: Source) -> list[RawPost]:
        posts: list[RawPost] = []
        seen_ids: set[str] = set()
        feed_cards = page.locator('[role="feed"] > div')
        containers = feed_cards.all() if feed_cards.count() else page.locator('[role="article"]').all()
        for article in containers[:self.max_posts]:
            content = self._post_message(article)
            if not content:
                continue
            links = article.locator("a").evaluate_all("links => links.map(link => link.href)")
            post_url = self._post_url(links)
            post_id = self._post_id(post_url, content)
            if post_id in seen_ids:
                continue
            seen_ids.add(post_id)
            posts.append(RawPost(post_id=post_id, source=source, content=content,
                collected_at=datetime.now(), post_url=post_url))
        return posts

    @staticmethod
    def _post_url(links: list[str]) -> str | None:
        """Resolve an article permalink while removing comment-specific query data."""
        for url in links:
            if "/posts/" in url and "comment_id=" not in url:
                # A post permalink may carry comment_id when Facebook rendered
                # the article around a comment; the path still identifies the
                # original post, so discard only query/fragment parts.
                return url.split("?", 1)[0].split("#", 1)[0]
        for url in links:
            if "/posts/" in url:
                return url.split("?", 1)[0].split("#", 1)[0]
        for url in links:
            if "story_fbid=" in url or "/permalink" in url:
                return url
        return None

    def _post_message(self, article) -> str | None:
        """Return only Facebook's post-message nodes, never article-wide text.

        Comments, author labels, reaction counts, and buttons live elsewhere in
        the article. Deliberately skipping unknown layouts is safer than using
        a broad fallback that can turn a comment into a lead.
        """
        for selector in self.POST_MESSAGE_SELECTORS:
            try:
                nodes = article.locator(selector)
                if nodes.count() == 0:
                    continue
                parts = [text.strip() for text in nodes.all_inner_texts() if text.strip()]
                if parts:
                    return "\n".join(dict.fromkeys(parts))
            except Exception:
                continue
        # Newer Facebook layouts may remove the data-ad message attributes.
        # Restrict the fallback to dir=auto nodes owned by the root article;
        # nested role=article nodes are comments and are intentionally ignored.
        try:
            fallback = article.evaluate(
                """root => {
                    const isArticleRoot = root.getAttribute('role') === 'article';
                    const candidates = [...root.querySelectorAll('[dir="auto"]')]
                      .filter(node => isArticleRoot
                        ? node.closest('[role="article"]') === root
                        : !node.closest('[role="article"]'))
                      .filter(node => !node.closest('[data-testid*="comment" i], [aria-label*="comment" i], [aria-label*="bình luận" i]'))
                      .map(node => (node.innerText || '').trim())
                      .filter(text => text.length >= 12)
                      .filter(text => !/^(like|comment|share|reply|see more|most relevant)$/i.test(text));
                    return candidates.sort((a, b) => b.length - a.length)[0] || null;
                }""", timeout=1_500
            )
            return fallback.strip() if fallback else None
        except Exception:
            # Facebook may detach/re-render an article while it is being read;
            # a stale article must not abort collection for every other source.
            return None
