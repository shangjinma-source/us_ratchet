"""Daily saved-source pipeline CLI. Clock and account paths are server-owned."""
import argparse
import json
from pathlib import Path
from data.strategy_daily_source_runner import run_daily_sources


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--config-path", required=True)
    parser.add_argument("--config-sha256", required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    result = run_daily_sources(root=args.root,
        configuration_bytes=Path(args.config_path).read_bytes(),
        configuration_sha256=args.config_sha256, execute=args.execute)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
