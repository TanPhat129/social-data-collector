from app.post_search import load_post_search, post_search_sources


def test_post_search_config_creates_independent_facebook_search_sources(tmp_path):
    path = tmp_path / "post_search.yaml"
    path.write_text("""facebook_post_search:
  queries: ["can tim gia su"]
  account_ids: [fb_001]
""", encoding="utf-8")
    config = load_post_search(str(path))
    source = post_search_sources(config)[0]
    assert source.id.startswith("fb_search_")
    assert source.source_url == "https://www.facebook.com/search/posts/?q=can%20tim%20gia%20su"
