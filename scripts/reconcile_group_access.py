"""Check every configured group against every account in one pool."""
import argparse
from pathlib import Path
import shutil

from app.config import get_settings
from app.database.postgres_coordinator import PostgresCoordinator
from app.group_candidate_service import GroupCandidateService
from app.orchestration.yaml_config import YamlOrchestrationConfig


def main() -> None:
    parser = argparse.ArgumentParser(description="Reconcile group access and assignments for all accounts in a pool.")
    parser.add_argument("--pool", required=True, help="pool ID from account_pools.yaml")
    args = parser.parse_args()
    settings = get_settings()
    if not settings.postgres_dsn:
        raise SystemExit("Set POSTGRES_DSN in .env")
    config = YamlOrchestrationConfig(settings.account_pools_path)
    document = config.load()
    config_path = Path(settings.account_pools_path)
    backup = config_path.with_suffix(config_path.suffix + ".before-access-reconcile.bak")
    shutil.copy2(config_path, backup)
    store = PostgresCoordinator(settings.postgres_dsn)
    store.initialize_schema()
    store.sync_yaml(document)
    result = GroupCandidateService(store, settings.account_pools_path).reconcile_existing_sources_for_pool(args.pool)
    store.sync_yaml(config.load())
    print(", ".join(f"{key}={value}" for key, value in result.items()))
    print(f"Backup: {backup}")


if __name__ == "__main__":
    main()
