"""Create or refresh the persistent Facebook browser profile for one UID.

Run with ``python -m scripts.login_facebook``. The user completes login and any
checkpoint in the visible browser window; this command never receives secrets.
"""
from app.config import get_settings
from app.presentation.facebook_auth import prepare_profile


def main() -> None:
    settings = get_settings()
    if not settings.facebook_browser_account_uid:
        raise SystemExit("Set FACEBOOK_BROWSER_ACCOUNT_UID in .env before running this command")
    prepare_profile(settings.facebook_browser_profile_root, settings.facebook_browser_account_uid)
    print(f"Facebook profile ready for UID {settings.facebook_browser_account_uid}.")


if __name__ == "__main__":
    main()
