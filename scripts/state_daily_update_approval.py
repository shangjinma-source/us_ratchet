r"""Plan, verify, or explicitly apply one hash-bound daily state transition.

Default is plan-only. This tool never creates orders or changes broker/config.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.state_daily_update_approval import (  # noqa: E402
    StateDailyUpdateApprovalError,
    apply_approved_plan,
    build_approval_plan,
    refresh_approval_plan,
    verify_approval_plan,
)

PREVIEW = ROOT / "data/cache/research/state_daily_update_preview_v1/manifest.json"
OUTPUT = ROOT / "data/cache/research/state_daily_update_approval_v1"
PLAN = OUTPUT / "approval_plan.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="一次性批准绑定的策略时钟推进")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--verify-only", action="store_true")
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--refresh-plan", action="store_true")
    parser.add_argument("--approval-token", default="")
    args = parser.parse_args()
    try:
        if args.refresh_plan:
            result, _ = refresh_approval_plan(
                PREVIEW, repository_root=ROOT, output_dir=OUTPUT,
            )
        elif args.verify_only:
            result = verify_approval_plan(PLAN, repository_root=ROOT)["plan"]
        elif args.apply:
            result = apply_approved_plan(
                PLAN, repository_root=ROOT, approval_token=args.approval_token,
                apply=True,
            )
        elif PLAN.exists():
            result = apply_approved_plan(
                PLAN, repository_root=ROOT, approval_token="", apply=False,
            )
        else:
            result, _ = build_approval_plan(
                PREVIEW, repository_root=ROOT, output_dir=OUTPUT,
            )
    except Exception as exc:
        print(f"daily-update approval fail-closed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({
        "status": result["status"],
        "request_id": result.get("request_id"),
        "session_date": result.get("session_date"),
        "apply_default": False,
        "state_written": result.get("state_written", False),
        "orders_created": False,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
