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

from backtest.ndx_portfolio_objective import (  # noqa: E402
    NdxPortfolioObjectiveError,
    build_objective_audit,
    file_sha256,
    load_objective_contract,
)


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate.resolve() if candidate.is_absolute() else (ROOT / candidate).resolve()


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
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


def _protected_hashes(paths: list[Path]) -> dict[str, str | None]:
    return {str(path): file_sha256(path) if path.is_file() else None for path in paths}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成 NDX 组合目标契约的只读研究审计快照。")
    parser.add_argument("--contract", default="config/ndx_portfolio_objective_v1.yaml")
    parser.add_argument("--fund-manifest", default="data/cache/funds/012922.csv.manifest.json")
    parser.add_argument("--fund-csv", default="data/cache/funds/012922.csv")
    parser.add_argument("--broker-snapshot", default="data/broker_positions.json")
    parser.add_argument("--output-dir", default="data/cache/research/ndx_portfolio_objective_v1")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    contract_path = _resolve(args.contract)
    fund_manifest_path = _resolve(args.fund_manifest)
    fund_csv_path = _resolve(args.fund_csv)
    broker_snapshot_path = _resolve(args.broker_snapshot)
    output_dir = _resolve(args.output_dir)
    audit_path = output_dir / "objective_audit.json"
    output_manifest_path = output_dir / "manifest.json"

    contract = load_objective_contract(contract_path)
    boundary = contract["mutation_boundary"]
    protected_paths = [_resolve(item) for item in boundary["protected_files"]]
    if any(output_dir == path or output_dir in path.parents for path in protected_paths):
        raise NdxPortfolioObjectiveError("research output cannot contain a protected live file")
    protected_before = _protected_hashes(protected_paths)

    audit = build_objective_audit(
        contract_path=contract_path,
        fund_manifest_path=fund_manifest_path,
        fund_csv_path=fund_csv_path,
        broker_snapshot_path=broker_snapshot_path,
    )
    generated_at = datetime.now(timezone.utc).isoformat()
    audit["generated_at"] = generated_at
    _atomic_write_json(audit_path, audit)

    output_manifest = {
        "schema_version": 1,
        "artifact_id": "ndx_portfolio_objective_audit_v1",
        "generated_at": generated_at,
        "output_path": str(audit_path),
        "output_sha256": file_sha256(audit_path),
        "contract_file_sha256": audit["contract"]["file_sha256"],
        "contract_canonical_sha256": audit["contract"]["canonical_sha256"],
        "evidence_flags": {
            "target_012922_nav_read": True,
            "broker_snapshot_read": True,
            "fresh_oos_consumed": False,
            "live_configuration_mutated": False,
            "state_mutated": False,
            "broker_snapshot_mutated": False,
            "today_advice_mutated": False,
            "orders_created": False,
        },
    }
    _atomic_write_json(output_manifest_path, output_manifest)

    protected_after = _protected_hashes(protected_paths)
    if protected_after != protected_before:
        raise NdxPortfolioObjectiveError("protected live files changed during the research audit")

    target = audit["target_012922"]["descriptive_snapshot"]
    print(
        "目标契约审计完成 | "
        f"contract={audit['contract']['canonical_sha256'][:16]} | "
        f"012922={target['data_end']} rows={target['row_count']} | "
        "live_mutation=False"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except NdxPortfolioObjectiveError as exc:
        print(f"目标契约审计失败: {exc}", file=sys.stderr)
        raise SystemExit(2)
