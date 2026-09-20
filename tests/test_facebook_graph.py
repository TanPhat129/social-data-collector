from app.collectors.facebook_graph import FacebookGraphCollector
from app.schemas import Source


def test_graph_collector_normalizes_posts_without_network(monkeypatch):
    pages = [{"data": [{"id": "post-1", "message": "Cần gia sư Toán", "created_time": "2026-01-01T10:00:00+0000", "permalink_url": "https://facebook.example/post-1"}]}]
    collector = FacebookGraphCollector("token", max_posts=10)
    monkeypatch.setattr(collector, "_request", lambda _url: pages.pop(0))

    posts = collector.collect(Source(id="odoo-1", external_id="group-123", name="Tutor group"))

    assert posts[0].post_id == "post-1"
    assert posts[0].source.external_id == "group-123"
    assert posts[0].post_url == "https://facebook.example/post-1"
