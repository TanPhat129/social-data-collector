"""Create/update the PostgreSQL schema and sync account-pool YAML."""
from app.config import get_settings
from app.database.postgres_coordinator import PostgresCoordinator
from app.orchestration.yaml_config import YamlOrchestrationConfig


def main() -> None:
    settings = get_settings()
    if not settings.postgres_dsn:
        raise SystemExit("Set POSTGRES_DSN in .env before initializing central storage")
    config = YamlOrchestrationConfig(settings.account_pools_path)
    document = config.load()
    database = PostgresCoordinator(settings.postgres_dsn)
    database.initialize_schema()
    database.sync_yaml(document)
    print(f"PostgreSQL initialized; synced {len(document.accounts)} accounts and {len(document.assignments)} assignments.")


if __name__ == "__main__":
    main()
