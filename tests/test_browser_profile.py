from app.collectors.facebook_browser import FacebookBrowserCollector


def test_browser_profile_is_isolated_by_uid():
    collector = FacebookBrowserCollector(".secrets/facebook-profiles", "100072588106800")
    assert collector.profile_path.replace("\\", "/").endswith("facebook-profiles/100072588106800")
