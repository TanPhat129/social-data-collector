import argparse
import logging

from app.config import get_settings
from app.core.container import Container
from app.schemas import Source
from app.database.postgres_coordinator import PostgresCoordinator
from app.group_discovery import FacebookGroupDiscovery, load_group_discovery
from app.orchestration.yaml_config import YamlOrchestrationConfig
from app.group_candidate_service import GroupCandidateService
from app.post_search import load_post_search, run_post_search


def configure_logging(debug: bool = False) -> None:
    logging.basicConfig(level=logging.DEBUG if debug else logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def run_once(container: Container) -> int:
    sync = container.sync_config()
    sources = sync.execute() if sync else [Source(id="demo-group", name="Demo Tutor Group")]
    total = sum(len(container.process_leads().execute(source)) for source in sources)
    logging.getLogger(__name__).info("accepted_leads=%d sources=%d", total, len(sources))
    return total


def run_group_discovery(settings, account_id: str) -> int:
    if not settings.postgres_dsn:
        raise ValueError("POSTGRES_DSN is required for group discovery")
    document = YamlOrchestrationConfig(settings.account_pools_path).load()
    account = next((item for item in document.accounts if item.id == account_id), None)
    if account is None:
        raise ValueError(f"Unknown account: {account_id}")
    discovery = load_group_discovery(settings.group_discovery_path)
    if not discovery.enabled or account.id not in discovery.account_ids:
        raise ValueError(f"Account {account.id} is not enabled in group_discovery.yaml")
    store = PostgresCoordinator(settings.postgres_dsn)
    # Schema upgrades are idempotent. Discovery must not fail merely because a
    # user initialized PostgreSQL before this optional workflow was added.
    store.initialize_schema()
    store.sync_yaml(document)
    saved = sum(store.save_group_candidate(account_id=account.id, **item) for item in FacebookGroupDiscovery().discover(account, discovery))
    logging.getLogger(__name__).info("group_candidates_saved=%d account=%s", saved, account.id)
    return saved


def show_and_recover_account_states(settings, *, interactive: bool = False) -> None:
    """Show account availability and recover stale locks only by explicit consent."""
    if not settings.postgres_dsn:
        raise ValueError("POSTGRES_DSN is required for account status")
    store = PostgresCoordinator(settings.postgres_dsn)
    states = store.list_account_states()
    for state in states:
        print(f"{state['account_id']}: status={state['status']} enabled={state['enabled']} updated_at={state['updated_at']}")
    stuck = [state for state in states if state["status"] == "IN_USE" and state["enabled"]]
    if not stuck:
        return
    ids = ", ".join(state["account_id"] for state in stuck)
    print(f"Stale candidate(s) in IN_USE: {ids}.")
    if interactive and input("Confirm every crawler terminal is stopped, then recover these accounts? [y/N]: ").strip().lower() == "y":
        print(f"Recovered {store.recover_in_use_accounts()} account(s) to AVAILABLE.")


def interactive_menu(settings, container: Container) -> None:
    """Small operator-facing entry point; non-interactive flags remain available."""
    document = YamlOrchestrationConfig(settings.account_pools_path).load()
    print("\nSOCIAL DATA COLLECTOR\n1. Crawl group — một account tìm group, tự gán các account có quyền xem\n2. Crawl post — từ group đã duyệt, tìm bài theo keyword\n3. Tìm post Facebook theo keyword\n4. Check / recover account status\n0. Thoát")
    choice = input("Chọn chức năng: ").strip()
    if choice == "1":
        accounts = ", ".join(item.id for item in document.accounts)
        account = input(f"Account chỉ dùng để tìm group ({accounts}): ").strip() or document.accounts[0].id
        if input(f"Tìm group bằng '{account}', rồi tự gán cho mọi account có quyền trong pool? [y/N]: ").strip().lower() == "y":
            run_group_discovery(settings, account)
            store = PostgresCoordinator(settings.postgres_dsn or "")
            store.initialize_schema()
            service = GroupCandidateService(store, settings.account_pools_path)
            counts = service.auto_assign_pending_for_discovery_account(account)
            pool = next(pool for pool in document.pools if account in pool.account_ids)
            reconciliation = service.reconcile_existing_sources_for_pool(pool.id, account)
            store.sync_yaml(YamlOrchestrationConfig(settings.account_pools_path).load())
            print("Kết quả: " + ", ".join(f"{key}={value}" for key, value in counts.items()))
            print("Đồng bộ quyền toàn bộ group: " + ", ".join(f"{key}={value}" for key, value in reconciliation.items()))
    elif choice == "2":
        mode = input("Chế độ [1=Test nhanh, 2=Quét toàn bộ, 3=Chạy liên tục] (1): ").strip() or "1"
        if input("Crawl post từ các group đã duyệt? [y/N]: ").strip().lower() == "y":
            runtime = container.central_runtime()
            if len(document.pools) > 1:
                print(f"Chạy tuần tự {len(document.pools)} pool nội bộ.")
            for pool in document.pools:
                print(f"Đang chạy nguồn đã duyệt: {pool.id}")
                if mode == "1":
                    first_shard = YamlOrchestrationConfig(settings.account_pools_path).shards(pool.id)[0]
                    runtime.run_round(pool.id, only_shard=first_shard, max_sources_total=5)
                elif mode == "2":
                    runtime.run_round(pool.id)
                elif mode == "3":
                    if len(document.pools) > 1:
                        runtime.run_continuously([item.id for item in document.pools])
                    else:
                        runtime.run_continuously([pool.id])
                else:
                    print("Chế độ không hợp lệ.")
                    break
    elif choice == "3":
        search_config = load_post_search(settings.post_search_path)
        enabled_accounts = [item.id for item in document.accounts if item.id in search_config.account_ids]
        if not enabled_accounts:
            print("Chưa có account nào được bật trong post_search.yaml.")
            return
        accounts = ", ".join(enabled_accounts)
        account = input(f"Account tìm post ({accounts}): ").strip() or enabled_accounts[0]
        if input(f"Tìm post Facebook theo keyword bằng '{account}'? [y/N]: ").strip().lower() == "y":
            accepted, exported = run_post_search(settings, container, account)
            print(f"Hoàn tất: accepted_leads={accepted}, sheet_exported={exported}")
    elif choice == "4":
        show_and_recover_account_states(settings, interactive=True)
    elif choice != "0":
        print("Lựa chọn không hợp lệ.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect tutor leads from permitted sources.")
    parser.add_argument("--schedule", action="store_true", help="run repeatedly at the configured interval")
    parser.add_argument("--prepare-facebook-profile", action="store_true", help="open a browser for an interactive Facebook login")
    parser.add_argument("--debug", action="store_true", help="log the reason every post is skipped or accepted")
    parser.add_argument("--orchestrate", action="store_true", help="run one central PostgreSQL account-pool crawl round")
    parser.add_argument("--pool", help="account pool ID in account_pools.yaml (required with --orchestrate)")
    parser.add_argument("--discover-groups", action="store_true", help="find group candidates; does not add any group to crawl assignments")
    parser.add_argument("--account", help="account ID for --discover-groups")
    parser.add_argument("--interactive", action="store_true", help="open the operator menu")
    parser.add_argument("--search-posts", action="store_true", help="search Facebook posts by configured queries, independently from group crawl")
    parser.add_argument("--shard", type=int, help="run only one shard with --orchestrate")
    parser.add_argument("--max-sources-per-account", type=int, help="limit groups per account with --orchestrate; useful for smoke tests")
    parser.add_argument("--max-sources-total", type=int, help="limit total groups across accounts with --orchestrate")
    parser.add_argument("--continuous", action="store_true", help="repeat full orchestrator rounds until Ctrl+C")
    parser.add_argument("--account-status", action="store_true", help="show central crawler-account states")
    parser.add_argument("--recover-in-use-accounts", action="store_true", help="recover IN_USE accounts after all crawler terminals have stopped")
    args = parser.parse_args()
    configure_logging(args.debug)
    settings = get_settings()
    if args.account_status or args.recover_in_use_accounts:
        if args.recover_in_use_accounts:
            if not settings.postgres_dsn:
                parser.error("POSTGRES_DSN is required for account recovery")
            store = PostgresCoordinator(settings.postgres_dsn)
            print(f"Recovered {store.recover_in_use_accounts()} IN_USE account(s) to AVAILABLE.")
        show_and_recover_account_states(settings)
        return
    if args.prepare_facebook_profile:
        if not settings.facebook_browser_account_uid:
            parser.error("FACEBOOK_BROWSER_ACCOUNT_UID must be set before preparing a profile")
        from app.presentation.facebook_auth import prepare_profile
        prepare_profile(settings.facebook_browser_profile_root, settings.facebook_browser_account_uid)
        return
    container = Container(settings)
    if args.interactive:
        if args.schedule or args.orchestrate or args.discover_groups:
            parser.error("--interactive cannot be combined with a run mode")
        interactive_menu(settings, container)
        return
    if args.discover_groups:
        if not args.account:
            parser.error("--account is required with --discover-groups")
        run_group_discovery(settings, args.account)
        return
    if args.search_posts:
        if not args.account:
            parser.error("--account is required with --search-posts")
        run_post_search(settings, container, args.account)
        return
    if args.orchestrate:
        if not args.pool:
            parser.error("--pool is required with --orchestrate")
        if args.schedule:
            parser.error("Central orchestration uses shard barriers; run one round per command, not --schedule")
        if args.continuous:
            if args.shard or args.max_sources_per_account or args.max_sources_total:
                parser.error("--continuous cannot be combined with smoke-test limits")
            container.central_runtime().run_continuously([args.pool])
        else:
            container.central_runtime().run_round(args.pool, only_shard=args.shard,
                                                  max_sources_per_account=args.max_sources_per_account,
                                                  max_sources_total=args.max_sources_total)
        return
    if not args.schedule:
        run_once(container)
        return
    from app.presentation.scheduler import run_scheduler
    run_scheduler(container)
