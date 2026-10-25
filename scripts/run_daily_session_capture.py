"""Pinned server source collection; no policy activation or account writes."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from data.strategy_daily_session_capture import capture_session


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--config-path", required=True)
    parser.add_argument("--config-sha256", required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    raw = Path(args.config_path).read_bytes()
    result = capture_session(root=args.root, configuration_bytes=raw,
                             configuration_sha256=args.config_sha256, execute=args.execute)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
