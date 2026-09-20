"""Interactive, user-controlled creation of a persistent Playwright profile."""
from pathlib import Path


def prepare_profile(profile_root: str, account_uid: str) -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("Install Playwright first: pip install -r requirements.txt && python -m playwright install chromium") from exc
    if not account_uid.isdecimal():
        raise ValueError("FACEBOOK_BROWSER_ACCOUNT_UID must be numeric")
    destination = Path(profile_root) / account_uid
    destination.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(str(destination), headless=False)
        page = context.new_page()
        page.goto("https://www.facebook.com/", wait_until="domcontentloaded")
        input(f"Log in as Facebook UID {account_uid}, complete any checkpoint, then press Enter here: ")
        uid = next((str(cookie["value"]) for cookie in context.cookies("https://www.facebook.com") if cookie.get("name") == "c_user"), None)
        if uid != account_uid:
            context.close()
            raise RuntimeError("Logged-in Facebook UID does not match FACEBOOK_BROWSER_ACCOUNT_UID; profile was not accepted")
        context.close()
