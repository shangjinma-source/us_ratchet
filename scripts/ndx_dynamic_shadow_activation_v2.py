r"""Rebuild activation-v2 readiness without registering any task.

PowerShell:
    python -B scripts\ndx_dynamic_shadow_activation_v2.py --readiness
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.ndx_dynamic_shadow_activation_v2 import (  # noqa: E402
    ACTIVATION_MANIFEST,
    NdxDynamicShadowActivationV2Error,
    SYNTHETIC_E2E_MANIFEST,
    build_activation_v2_manifest,
    build_activation_v2_readiness,
    build_synthetic_e2e_manifest,
    verify_activation_v2_manifest,
)
from data.versioning import file_sha256  # noqa: E402


OUTPUT_ROOT = ROOT / "data/cache/research/ndx_dynamic_shadow_activation_v2"
PROTECTED = (
    ROOT / "config/config.yaml",
    ROOT / "data/state.json",
    ROOT / "data/broker_positions.json",
)


def _hashes() -> dict[str, str | None]:
    return {
        path.relative_to(ROOT).as_posix(): file_sha256(path) if path.is_file() else None
        for path in PROTECTED
    }


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n"
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rebuild research-only dynamic-shadow activation-v2 readiness",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--readiness", action="store_true")
    mode.add_argument("--build-synthetic-e2e", action="store_true")
    mode.add_argument("--build-activation-manifest", action="store_true")
    mode.add_argument("--verify-activation-manifest", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    before = _hashes()
    try:
        if args.build_synthetic_e2e:
            result = build_synthetic_e2e_manifest(
                (ROOT / SYNTHETIC_E2E_MANIFEST).parent, repository_root=ROOT,
            )
        elif args.build_activation_manifest:
            result = build_activation_v2_manifest(ROOT)
            activation_path = ROOT / ACTIVATION_MANIFEST
            _atomic_json(activation_path, result)
            result = verify_activation_v2_manifest(activation_path, repository_root=ROOT)
        elif args.verify_activation_manifest:
            result = verify_activation_v2_manifest(
                ROOT / ACTIVATION_MANIFEST, repository_root=ROOT,
            )
        else:
            result = build_activation_v2_readiness(ROOT)
        if _hashes() != before:
            raise NdxDynamicShadowActivationV2Error("protected live files changed")
        payload = result
        if not (args.build_synthetic_e2e or args.build_activation_manifest or args.verify_activation_manifest):
            payload = {
                **result,
                "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                "activation_manifest_written": False,
                "automation_registered": False,
            }
            _atomic_json(OUTPUT_ROOT / "readiness.json", payload)
    except Exception as exc:
        failure = {
            "schema_version": 2,
            "manifest_type": "ndx_dynamic_shadow_activation_v2_failure",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "status": "BLOCKED_FAIL_CLOSED",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "research_automation_registration_allowed": False,
            "promotion_allowed": False,
            "live_mutation_allowed": False,
        }
        _atomic_json(OUTPUT_ROOT / "last_failure.json", failure)
        print(f"activation v2 fail-closed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(
        "dynamic shadow activation v2 | "
        f"status={payload['status']} | "
        f"registration_allowed={payload.get('research_automation_registration_allowed', False)} | "
        "automation_registered=False | promotion=False | live=False"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
