import argparse
import logging

from app.config import get_settings
from app.core.container import Container
from app.schemas import Source


def configure_logging(debug: bool = False) -> None:
    logging.basicConfig(level=logging.DEBUG if debug else logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def run_once(container: Container) -> int:
    sync = container.sync_config()
    sources = sync.execute() if sync else [Source(id="demo-group", name="Demo Tutor Group")]
    total = sum(len(container.process_leads().execute(source)) for source in sources)
    logging.getLogger(__name__).info("accepted_leads=%d sources=%d", total, len(sources))
    return total


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect tutor leads from permitted sources.")
    parser.add_argument("--schedule", action="store_true", help="run repeatedly at the configured interval")
    parser.add_argument("--prepare-facebook-profile", action="store_true", help="open a browser for an interactive Facebook login")
    parser.add_argument("--debug", action="store_true", help="log the reason every post is skipped or accepted")
    args = parser.parse_args()
    configure_logging(args.debug)
    settings = get_settings()
    if args.prepare_facebook_profile:
        if not settings.facebook_browser_account_uid:
            parser.error("FACEBOOK_BROWSER_ACCOUNT_UID must be set before preparing a profile")
        from app.presentation.facebook_auth import prepare_profile
        prepare_profile(settings.facebook_browser_profile_root, settings.facebook_browser_account_uid)
        return
    container = Container(settings)
    if not args.schedule:
        run_once(container)
        return
    from app.presentation.scheduler import run_scheduler
    run_scheduler(container)
