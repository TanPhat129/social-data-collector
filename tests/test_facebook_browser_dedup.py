from app.collectors.facebook_browser import FacebookBrowserCollector


def test_post_id_is_stable_for_same_permalink():
    collector = FacebookBrowserCollector(".secrets/profiles", "100072588106800")
    url = "https://www.facebook.com/groups/g/posts/123/"
    assert collector._post_id(url, "first") == collector._post_id(url, "updated text")
