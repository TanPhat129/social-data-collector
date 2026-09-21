"""Playwright connector for Facebook sources visible to an authorized session.

It deliberately does not automate login, solve challenges, or evade platform
controls. Create the persistent profile interactively outside this application.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import logging
from pathlib import Path
import re
import unicodedata
from urllib.parse import parse_qs, urlparse

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
    RELATIVE_TIME = re.compile(
        r"(?<!\d)(?P<amount>\d+)\s*(?P<unit>phút|phut|minutes?|mins?|giờ|gio|hours?|hrs?|ngày|ngay|days?|h)(?!\w)",
        re.IGNORECASE,
    )
    # Accent-folded before matching so labels such as "21 giờ" work regardless
    # of the UI's Unicode normalization.
    RELATIVE_TIME = re.compile(
        r"(?<!\d)(?P<amount>\d+)\s*(?P<unit>phut|minutes?|mins?|gio|hours?|hrs?|ngay|days?|h)(?!\w)",
        re.IGNORECASE,
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
            author_url = None if self._is_anonymous_post(article, content) else self._author_url(self._header_links(article))
            if author_url:
                author_url = self._resolve_author_url(page, author_url)
            post_id = self._post_id(post_url, content)
            if post_id in seen_ids:
                continue
            seen_ids.add(post_id)
            collected_at = datetime.now().astimezone()
            posts.append(RawPost(post_id=post_id, source=source, content=content,
                collected_at=collected_at, posted_at=self._posted_at(article, collected_at, page), post_url=post_url,
                author_url=author_url))
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

    @staticmethod
    def _author_url(links: list[str]) -> str | None:
        """Return the first plausible Facebook profile link in post-header order."""
        ignored_paths = {"groups", "posts", "permalink", "reel", "reels", "watch", "photo", "photos", "events", "marketplace"}
        for url in links:
            parsed = urlparse(url)
            if parsed.scheme != "https" or parsed.netloc.lower() not in {"facebook.com", "www.facebook.com", "m.facebook.com"}:
                continue
            if parsed.path == "/profile.php":
                profile_id = parse_qs(parsed.query).get("id", [None])[0]
                if profile_id and profile_id.isdecimal():
                    return f"https://www.facebook.com/profile.php?id={profile_id}"
                continue
            parts = [part for part in parsed.path.split("/") if part]
            if len(parts) == 4 and parts[0].lower() == "groups" and parts[2].lower() == "user" and parts[1].isdecimal() and parts[3].isdecimal():
                # Facebook frequently exposes a group-member URL instead of a
                # public profile URL. It is an authenticated, exact link to
                # the post author and can be resolved in a separate tab.
                return f"https://www.facebook.com/groups/{parts[1]}/user/{parts[3]}/"
            if len(parts) == 1 and parts[0].lower() not in ignored_paths:
                return f"https://www.facebook.com/{parts[0]}"
        return None

    def _header_links(self, article) -> list[str]:
        """Return links in the header preceding a semantic post-message node.

        Comment links occur after the post body. If Facebook does not expose a
        reliable post-message node, return no author link rather than risk
        attaching a commenter to an anonymous post.
        """
        try:
            return article.evaluate(
                """(root, selectors) => {
                    const message = selectors.map(selector => root.querySelector(selector)).find(Boolean);
                    if (!message) return [];
                    return [...root.querySelectorAll('a[href]')]
                        .filter(link => Boolean(link.compareDocumentPosition(message) & Node.DOCUMENT_POSITION_FOLLOWING))
                        .map(link => link.href);
                }""", list(self.POST_MESSAGE_SELECTORS), timeout=1_500
            )
        except Exception:
            return []

    @staticmethod
    def _is_anonymous_text(text: str) -> bool:
        folded = unicodedata.normalize("NFD", text).lower()
        folded = "".join(char for char in folded if not unicodedata.combining(char))
        return "nguoi tham gia an danh" in folded or "anonymous participant" in folded

    def _is_anonymous_post(self, article, content: str) -> bool:
        """Check only the post header, never text from comments."""
        try:
            header_text = article.evaluate(
                """(root, body) => {
                    const text = root.innerText || '';
                    const index = text.indexOf(body);
                    return index >= 0 ? text.slice(0, index) : '';
                }""", content, timeout=1_500
            )
            return self._is_anonymous_text(header_text)
        except Exception:
            return False

    def _resolve_author_url(self, page, author_url: str) -> str:
        """Open a non-anonymous author destination in a temporary tab.

        Group-member links are what Facebook currently renders for many group
        posts. Visiting the destination is equivalent to opening its avatar,
        but avoids coordinate-based clicking that could hit a group or comment
        avatar. If Facebook does not redirect to a public profile, retain the
        exact group-member URL because it still opens that member for the
        authenticated account.
        """
        if "/groups/" not in author_url or "/user/" not in author_url:
            return author_url
        detail_page = page.context.new_page()
        try:
            detail_page.goto(author_url, wait_until="domcontentloaded", timeout=20_000)
            resolved = self._author_url([detail_page.url])
            return resolved or author_url
        except Exception as exc:
            logger.debug("author_url=%s resolution_failed=%s", author_url, type(exc).__name__)
            return author_url
        finally:
            detail_page.close()

    @staticmethod
    def _posted_at(article, observed_at: datetime | None = None) -> datetime | None:
        """Read a timestamp belonging to the post card, never a comment.

        Modern Facebook can expose an epoch value, an ISO ``datetime`` value,
        or only a human-readable relative label. We use only the first two;
        guessing from labels such as ``2 giờ`` risks an incorrect date.
        """
        try:
            values = article.evaluate(
                """root => {
                    const isCommentRoot = root.getAttribute('role') === 'article';
                    const belongsToPost = node => {
                        const comment = node.closest('[role="article"]');
                        return isCommentRoot ? comment === root : !comment;
                    };
                    const own = selector => [...root.querySelectorAll(selector)]
                        .filter(belongsToPost);
                    const epoch = own('abbr[data-utime], [data-utime]')
                        .map(node => node.getAttribute('data-utime')).filter(Boolean);
                    if (epoch.length) return epoch;
                    const iso = own('time[datetime]')
                        .map(node => node.getAttribute('datetime')).filter(Boolean);
                    if (iso.length) return iso;
                    const relative = own('a[href*="/posts/"], a[href*="story_fbid="], a[href*="/permalink"]')
                        .map(node => node.innerText || node.getAttribute('aria-label') || '')
                        .filter(Boolean);
                    return relative.map(value => `relative:${value}`);
                }""", timeout=1_500
            )
        except Exception:
            return None
        observed_at = observed_at or datetime.now(timezone.utc)
        if observed_at.tzinfo is None:
            observed_at = observed_at.replace(tzinfo=timezone.utc)
        for value in values:
            try:
                if str(value).startswith("relative:"):
                    relative_text = unicodedata.normalize("NFD", str(value)[len("relative:"):])
                    relative_text = "".join(char for char in relative_text if not unicodedata.combining(char))
                    relative_match = FacebookBrowserCollector.RELATIVE_TIME.search(relative_text)
                    if not relative_match:
                        continue
                    amount = int(relative_match.group("amount"))
                    unit = relative_match.group("unit").lower()
                    seconds = amount * (60 if unit in {"phút", "phut", "minute", "minutes", "min", "mins"}
                                        else 3_600 if unit in {"giờ", "gio", "hour", "hours", "hr", "hrs", "h"}
                                        else 86_400)
                    return observed_at - timedelta(seconds=seconds)
                if str(value).strip().lstrip("-").isdigit():
                    epoch = int(value)
                    if epoch > 10_000_000_000:
                        epoch //= 1000
                    return datetime.fromtimestamp(epoch, tz=observed_at.tzinfo)
                timestamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                if timestamp.tzinfo is None:
                    return timestamp.replace(tzinfo=observed_at.tzinfo)
                return timestamp.astimezone(observed_at.tzinfo)
            except (TypeError, ValueError, OverflowError):
                pass
        return None

    @staticmethod
    def _posted_at(article, observed_at: datetime | None = None, page=None) -> datetime | None:
        """Get a post timestamp from metadata or Facebook's hover tooltip.

        The time link in newer group cards often has a query-only ``href`` and
        an empty text node until it is hovered. It appears immediately after
        the author header link. Comments are excluded before considering any
        timestamp candidate.
        """
        try:
            metadata = article.evaluate(
                """root => {
                    const isCommentRoot = root.getAttribute('role') === 'article';
                    const belongsToPost = node => {
                        const comment = node.closest('[role="article"]');
                        return isCommentRoot ? comment === root : !comment;
                    };
                    const anchors = [...root.querySelectorAll('a')];
                    const ownAnchors = anchors.map((node, index) => ({node, index}))
                        .filter(item => belongsToPost(item.node));
                    const own = selector => [...root.querySelectorAll(selector)].filter(belongsToPost);
                    const values = [
                        ...own('abbr[data-utime], [data-utime]').map(node => node.getAttribute('data-utime')),
                        ...own('time[datetime]').map(node => node.getAttribute('datetime')),
                        ...ownAnchors.map(item => item.node.getAttribute('aria-label') || item.node.getAttribute('data-tooltip-content')),
                        ...ownAnchors.map(item => {
                            const text = (item.node.innerText || '').trim();
                            return text ? `relative:${text}` : null;
                        }),
                    ].filter(Boolean);
                    const authorPosition = ownAnchors.findIndex(item =>
                        /\/groups\/[^/]+\/user\/\d+/.test(item.node.href || '') ||
                        /\/profile\.php\?id=\d+/.test(item.node.href || '')
                    );
                    const timestamp = ownAnchors.find(item => {
                        const href = item.node.getAttribute('href') || '';
                        return item.index > (authorPosition >= 0 ? ownAnchors[authorPosition].index : -1) &&
                            (/^[?#]/.test(href) || /\/posts\/|story_fbid=|permalink/.test(href));
                    });
                    return {values, hoverIndex: timestamp ? timestamp.index : null};
                }""", timeout=1_500
            )
        except Exception:
            return None

        if not isinstance(metadata, dict):
            metadata = {"values": metadata, "hoverIndex": None}
        observed_at = observed_at or datetime.now(timezone.utc)
        if observed_at.tzinfo is None:
            observed_at = observed_at.replace(tzinfo=timezone.utc)

        def parse(values) -> datetime | None:
            for value in values:
                raw = str(value).strip()
                absolute = re.search(r"(?P<day>\d{1,2})\D+(?P<month>\d{1,2}),\s*(?P<year>\d{4})\D+(?P<hour>\d{1,2}):(?P<minute>\d{2})", raw)
                if absolute:
                    try:
                        return datetime(
                            int(absolute.group("year")), int(absolute.group("month")), int(absolute.group("day")),
                            int(absolute.group("hour")), int(absolute.group("minute")), tzinfo=observed_at.tzinfo,
                        )
                    except ValueError:
                        continue
                try:
                    if raw.lstrip("-").isdigit():
                        epoch = int(raw)
                        return datetime.fromtimestamp(epoch // 1000 if epoch > 10_000_000_000 else epoch, tz=observed_at.tzinfo)
                    if raw.startswith("relative:"):
                        folded = unicodedata.normalize("NFD", raw[len("relative:"):])
                        folded = "".join(char for char in folded if not unicodedata.combining(char))
                        relative = FacebookBrowserCollector.RELATIVE_TIME.search(folded)
                        if not relative:
                            continue
                        amount, unit = int(relative.group("amount")), relative.group("unit").lower()
                        seconds = amount * (60 if unit in {"phut", "minute", "minutes", "min", "mins"}
                                            else 3_600 if unit in {"gio", "hour", "hours", "hr", "hrs", "h"}
                                            else 86_400)
                        return observed_at - timedelta(seconds=seconds)
                    timestamp = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                    return timestamp.replace(tzinfo=observed_at.tzinfo) if timestamp.tzinfo is None else timestamp.astimezone(observed_at.tzinfo)
                except (TypeError, ValueError, OverflowError):
                    continue
            return None

        posted_at = parse(metadata.get("values", []))
        if posted_at or page is None or metadata.get("hoverIndex") is None:
            return posted_at
        try:
            timestamp_link = article.locator("a").nth(metadata["hoverIndex"])
            timestamp_link.hover(timeout=1_500)
            page.wait_for_timeout(300)
            tooltip_values = page.locator('[role="tooltip"]').all_inner_texts()
            tooltip_values.extend(timestamp_link.evaluate("node => [node.getAttribute('aria-label'), node.getAttribute('data-tooltip-content'), node.innerText]"))
            return parse(tooltip_values)
        except Exception:
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
