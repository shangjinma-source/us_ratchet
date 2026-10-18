"""Research-only source freeze and economic replay CLI for canonical v5 P4."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.ndx_dynamic_shadow_p4_replay import (  # noqa: E402
    canonical_replay_bundle_path,
    freeze_p4_replay_source_bundle,
    verify_p4_economic_replay,
)


def _latest_run() -> tuple[Path, str]:
    latest_path = ROOT / "data/cache/research/ndx_challenger_forward_v5/latest_evaluation/manifest.json"
    latest = json.loads(latest_path.read_text(encoding="utf-8"))
    item = latest.get("immutable_evaluation_run") or {}
    return Path(str(item.get("path") or "")), str(item.get("evaluation_run_id") or "")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Freeze and replay canonical v5 P4 economic evidence (research only)",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--freeze-sources", action="store_true")
    mode.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    run_path, run_id = _latest_run()
    if args.freeze_sources:
        result = freeze_p4_replay_source_bundle(run_path, repository_root=ROOT)
    else:
        result = verify_p4_economic_replay(
            canonical_replay_bundle_path(run_id, repository_root=ROOT),
            repository_root=ROOT,
        )
        # Data frames are evidence used by the caller, not JSON manifest fields.
        result = {
            key: value for key, value in result.items()
            if key not in {"summary", "research_track_summary"}
        }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"P4 economic replay failed closed: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(2)
