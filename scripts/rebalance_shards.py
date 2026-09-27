"""Rebalance existing assignments without changing their account ownership."""
import argparse
from collections import Counter, defaultdict
from pathlib import Path
import shutil

import yaml

from app.config import get_settings
from app.orchestration.yaml_config import YamlOrchestrationConfig


def rebalance(values: dict, max_groups_per_account_shard: int) -> tuple[dict, Counter]:
    assignments = values.get("assignments", [])
    buckets: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for assignment in assignments:
        buckets[(assignment["pool_id"], assignment["account_id"])].append(assignment)

    counts: Counter = Counter()
    for (_, _), items in buckets.items():
        # Preserve the configured source order.  Account ownership, enabled,
        # backup and priority values are intentionally untouched.
        for position, assignment in enumerate(items):
            assignment["shard"] = position // max_groups_per_account_shard + 1
            counts[(assignment["pool_id"], assignment["account_id"], assignment["shard"])] += 1
    return values, counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebalance group assignments into bounded shards.")
    parser.add_argument("--max-groups-per-account-shard", type=int, default=10)
    parser.add_argument("--apply", action="store_true", help="write YAML after creating a .bak backup")
    args = parser.parse_args()
    if args.max_groups_per_account_shard < 1:
        parser.error("--max-groups-per-account-shard must be at least 1")

    path = Path(get_settings().account_pools_path)
    values = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    values, counts = rebalance(values, args.max_groups_per_account_shard)
    for (pool_id, account_id, shard), count in sorted(counts.items()):
        print(f"pool={pool_id} account={account_id} shard={shard} groups={count}")
    if not args.apply:
        print("Dry run only. Re-run with --apply to save this layout.")
        return

    backup = path.with_suffix(path.suffix + ".bak")
    shutil.copy2(path, backup)
    path.write_text(yaml.safe_dump(values, allow_unicode=True, sort_keys=False), encoding="utf-8")
    # Validate the written file before reporting success.
    YamlOrchestrationConfig(str(path)).load()
    print(f"Updated {path}; backup created at {backup}.")


if __name__ == "__main__":
    main()
