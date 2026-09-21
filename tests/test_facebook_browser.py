from app.collectors.facebook_browser import FacebookBrowserCollector
from datetime import datetime, timezone


class FakeNodes:
    def __init__(self, text): self.text = text
    def count(self): return len(self.text)
    def all_inner_texts(self): return self.text


class FakeArticle:
    def __init__(self, messages): self.messages = messages
    def locator(self, selector): return FakeNodes(self.messages.get(selector, []))


def test_browser_collector_uses_only_post_message_nodes():
    collector = FacebookBrowserCollector(".secrets/profiles", "100072588106800")
    article = FakeArticle({'[data-ad-comet-preview="message"]': ["Cần gia sư Toán", "Cần gia sư Toán"]})
    assert collector._post_message(article) == "Cần gia sư Toán"


def test_browser_collector_skips_unknown_article_instead_of_comments():
    collector = FacebookBrowserCollector(".secrets/profiles", "100072588106800")
    assert collector._post_message(FakeArticle({})) is None


def test_browser_collector_keeps_post_path_and_removes_comment_query():
    links = ["https://www.facebook.com/groups/g/posts/123/?comment_id=456"]
    assert FacebookBrowserCollector._post_url(links) == "https://www.facebook.com/groups/g/posts/123/"


def test_browser_collector_extracts_only_canonical_author_profile_urls():
    links = [
        "https://www.facebook.com/profile.php?id=123456&__tn__=x",
        "https://www.facebook.com/groups/tutor/posts/999/",
        "https://www.facebook.com/profile.php?id=comment-author",
    ]
    assert FacebookBrowserCollector._author_url(links) == "https://www.facebook.com/profile.php?id=123456"


def test_browser_collector_skips_group_and_post_links_as_author_urls():
    links = ["https://www.facebook.com/groups/tutor/", "https://www.facebook.com/groups/tutor/posts/999/"]
    assert FacebookBrowserCollector._author_url(links) is None


def test_browser_collector_keeps_group_member_link_for_author_resolution():
    links = [
        "https://www.facebook.com/groups/2039048736388431/user/61593091064048/?__tn__=R",
        "https://www.facebook.com/groups/2039048736388431/posts/4050092828617335/",
    ]
    assert FacebookBrowserCollector._author_url(links) == (
        "https://www.facebook.com/groups/2039048736388431/user/61593091064048/"
    )


def test_browser_collector_recognizes_vietnamese_anonymous_post_header():
    assert FacebookBrowserCollector._is_anonymous_text("Người tham gia ẩn danh")


def test_browser_collector_does_not_treat_normal_author_as_anonymous():
    assert not FacebookBrowserCollector._is_anonymous_text("Hà Phan Thanh · 1 giờ")


def test_browser_collector_reads_epoch_timestamp_from_post_metadata():
    class Article:
        def evaluate(self, _script, timeout):
            return ["1726822800"]

    posted_at = FacebookBrowserCollector._posted_at(Article())
    assert posted_at is not None
    assert posted_at.tzinfo == timezone.utc
    assert posted_at.isoformat() == "2024-09-20T09:00:00+00:00"


def test_browser_collector_leaves_unparseable_timestamp_empty():
    class Article:
        def evaluate(self, _script, timeout):
            return ["2 gio"]

    assert FacebookBrowserCollector._posted_at(Article()) is None


def test_browser_collector_converts_relative_hours_from_collection_time():
    class Article:
        def evaluate(self, _script, timeout):
            return ["relative:21 giờ"]

    observed_at = datetime(2026, 9, 21, 15, 0, tzinfo=timezone.utc)
    posted_at = FacebookBrowserCollector._posted_at(Article(), observed_at)
    assert posted_at == datetime(2026, 9, 20, 18, 0, tzinfo=timezone.utc)


def test_browser_collector_prefers_absolute_facebook_tooltip_time():
    class Article:
        def evaluate(self, _script, timeout):
            return ["Thứ Hai, 21 Tháng 9, 2026 lúc 13:47"]

    observed_at = datetime(2026, 9, 21, 14, 30, tzinfo=timezone.utc)
    posted_at = FacebookBrowserCollector._posted_at(Article(), observed_at)
    assert posted_at == datetime(2026, 9, 21, 13, 47, tzinfo=timezone.utc)
