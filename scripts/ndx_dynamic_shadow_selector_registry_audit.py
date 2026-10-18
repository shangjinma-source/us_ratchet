from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.ndx_dynamic_shadow_selector_registry import (  # noqa: E402
    NdxDynamicShadowSelectorRegistryError,
    build_dynamic_shadow_selector_registry_audit,
)
from backtest.ndx_portfolio_objective import file_sha256  # noqa: E402


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate.resolve() if candidate.is_absolute() else (ROOT / candidate).resolve()


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


def _hashes(paths: list[Path]) -> dict[str, str | None]:
    return {str(path): file_sha256(path) if path.is_file() else None for path in paths}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="审计 inactive 动态 shadow selector 注册表。")
    parser.add_argument("--registry", default="config/ndx_dynamic_shadow_selector_registry_v1.yaml")
    parser.add_argument("--objective", default="config/ndx_portfolio_objective_v1.yaml")
    parser.add_argument("--dynamic-walkforward", default="config/ndx_dynamic_walkforward_v1.yaml")
    parser.add_argument("--selector-policy-module", default="backtest/ndx_dynamic_candidate_policy.py")
    parser.add_argument(
        "--output-dir",
        default="data/cache/research/ndx_dynamic_shadow_selector_registry_v1",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    registry_path = _resolve(args.registry)
    objective_path = _resolve(args.objective)
    walkforward_path = _resolve(args.dynamic_walkforward)
    policy_module_path = _resolve(args.selector_policy_module)
    output_dir = _resolve(args.output_dir)
    audit_path = output_dir / "selector_registry_audit.json"
    manifest_path = output_dir / "manifest.json"

    protected = [
        _resolve("config/config.yaml"),
        _resolve("data/state.json"),
        _resolve("data/broker_positions.json"),
    ]
    protected_before = _hashes(protected)
    audit = build_dynamic_shadow_selector_registry_audit(
        registry_path=registry_path,
        objective_path=objective_path,
        dynamic_walkforward_path=walkforward_path,
        selector_policy_module_path=policy_module_path,
    )
    generated_at = datetime.now(timezone.utc).isoformat()
    audit["generated_at"] = generated_at
    _atomic_json(audit_path, audit)
    manifest = {
        "schema_version": 1,
        "artifact_id": "ndx_dynamic_shadow_selector_registry_audit_v1",
        "generated_at": generated_at,
        "output_path": str(audit_path),
        "output_sha256": file_sha256(audit_path),
        "registry_file_sha256": audit["registry"]["file_sha256"],
        "registry_canonical_sha256": audit["registry"]["canonical_sha256"],
        "active": False,
        "runner_registered": False,
        "automation_enabled": False,
        "live_mutation": False,
    }
    _atomic_json(manifest_path, manifest)
    if _hashes(protected) != protected_before:
        raise NdxDynamicShadowSelectorRegistryError("protected live files changed during selector audit")

    print(
        "动态 shadow selector 审计完成 | "
        f"selectors={audit['registry']['selector_count']} | "
        f"registry={audit['registry']['canonical_sha256'][:16]} | "
        "active=False | live_mutation=False"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except NdxDynamicShadowSelectorRegistryError as exc:
        print(f"动态 shadow selector 审计失败: {exc}", file=sys.stderr)
        raise SystemExit(2)
