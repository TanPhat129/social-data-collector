"""Show or explicitly recover central account states without exposing credentials."""
import argparse
from app.config import get_settings
from app.database.postgres_coordinator import PostgresCoordinator
from app.orchestration.models import AccountStatus


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect central Facebook crawler account states.")
    parser.add_argument(
        "--recover-in-use",
        action="store_true",
        help="set IN_USE accounts back to AVAILABLE; use only after every crawler terminal has stopped",
    )
    parser.add_argument(
        "--mark-available",
        metavar="ACCOUNT_ID",
        help="mark one account AVAILABLE only after its Facebook profile has been checked manually",
    )
    parser.add_argument("--access-summary", metavar="ACCOUNT_ID", help="show group-access validation counts for one account")
    args = parser.parse_args()
    settings = get_settings()
    if not settings.postgres_dsn:
        raise SystemExit("Set POSTGRES_DSN in .env")
    store = PostgresCoordinator(settings.postgres_dsn)
    if args.recover_in_use:
        changed = store.recover_in_use_accounts()
        print(f"Recovered {changed} IN_USE account(s) to AVAILABLE.")
    if args.mark_available:
        known_ids = {account["account_id"] for account in store.list_account_states()}
        if args.mark_available not in known_ids:
            raise SystemExit(f"Unknown account: {args.mark_available}")
        store.release_account(args.mark_available, AccountStatus.AVAILABLE)
        print(f"Marked {args.mark_available} AVAILABLE.")
    if args.access_summary:
        summary = store.group_access_summary(args.access_summary)
        if not summary:
            print(f"No group-access validation has been recorded for {args.access_summary}.")
        for item in summary:
            print(f"{args.access_summary}: {item['status']}={item['groups']}")
    for account in store.list_account_states():
        print(f"{account['account_id']}: status={account['status']} enabled={account['enabled']} updated_at={account['updated_at']}")


if __name__ == "__main__":
    main()
