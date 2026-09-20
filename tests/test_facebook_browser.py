from app.collectors.facebook_browser import FacebookBrowserCollector


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
