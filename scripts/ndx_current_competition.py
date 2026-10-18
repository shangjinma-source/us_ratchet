"""Build the hash-locked v11 current quality and risk-chain competition bundle."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.ndx_current_competition import (  # noqa: E402
    CURRENT_COMPETITION_POLICY_ID,
    build_current_competition,
    build_current_quality_scores,
    load_local_price_series,
)
from backtest.ndx_marginal_stage1 import verify_sidecar  # noqa: E402
from core.helpers import atomic_write_text  # noqa: E402
from data.versioning import file_sha256, utc_now_iso, write_dataset_manifest  # noqa: E402


def _resolve(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def _write_versioned(frame: pd.DataFrame, path: Path, key: str, *, extra: dict) -> dict:
    frame.to_csv(path, index=False, encoding="utf-8-sig")
    return write_dataset_manifest(
        path,
        dataset_type="ndx_v11_current_competition",
        dataset_key=key,
        source="derived_from_hash_locked_local_evidence",
        source_locator=None,
        fetched_at=utc_now_iso(),
        fetched_at_evidence="bundle_generation_utc",
        row_count=len(frame),
        data_start="2026-07-13",
        data_end="2026-07-13",
        extra=extra,
    )


def build_bundle(args) -> dict:
    factor_path = _resolve(args.factors)
    taxonomy_path = _resolve(args.taxonomy)
    valuation_path = _resolve(args.valuation_scores)
    output = _resolve(args.output_dir)
    factor_version = verify_sidecar(factor_path)
    taxonomy_version = verify_sidecar(taxonomy_path)
    valuation_version = verify_sidecar(valuation_path)
    factors = pd.read_csv(factor_path, low_memory=False)
    taxonomy = pd.read_csv(taxonomy_path, low_memory=False)
    valuation_scores = pd.read_csv(valuation_path, low_memory=False)
    if len(factors) != 101 or len(taxonomy) != 101 or len(valuation_scores) != 101:
        raise ValueError(
            "current competition requires exactly 101 factor, taxonomy, and valuation rows"
        )
    scores, factor_audit, coverage = build_current_quality_scores(factors)
    price_series, price_inventory = load_local_price_series(
        taxonomy["ticker"].astype(str).tolist(), cache_dir=_resolve(args.price_cache_dir)
    )
    competition, shortlist = build_current_competition(
        taxonomy,
        scores,
        price_series,
        selection_date=args.selection_date,
        lookback_days=args.lookback_days,
        min_history_days=args.lookback_days + 1,
        valuation_scores=valuation_scores,
    )
    output.mkdir(parents=True, exist_ok=True)
    common = {
        "return_data_read": True,
        "return_data_role": "signal_formation_only_not_oos_evaluation",
        "fresh_oos_consumed": False,
        "live_config_changed": False,
        "state_changed": False,
        "today_advice_changed": False,
        "policy_id": CURRENT_COMPETITION_POLICY_ID,
    }
    artifacts = {}
    for key, frame in {
        "quality_scores": scores,
        "quality_factor_audit": factor_audit,
        "quality_coverage": coverage,
        "price_inventory": price_inventory,
        "candidate_competition": competition,
        "risk_chain_shortlist": shortlist,
    }.items():
        path = output / f"{key}.csv"
        version = _write_versioned(frame, path, key, extra=common)
        artifacts[key] = {
            "path": path.as_posix(),
            "rows": len(frame),
            "sha256": version["content_sha256"],
            "version_id": version["version_id"],
        }
    workbook = output / "ndx_current_competition.xlsx"
    temporary = output / "ndx_current_competition.tmp.xlsx"
    try:
        with pd.ExcelWriter(temporary, engine="openpyxl") as writer:
            pd.DataFrame([
                {"项目": "状态", "值": "RESEARCH_SHORTLIST_ONLY_NOT_ADMITTED"},
                {"项目": "证券数", "值": len(competition)},
                {"项目": "质量评分合格数", "值": int(scores["quality_eligible"].sum())},
                {"项目": "竞赛合格数", "值": int(competition["competition_eligible"].sum())},
                {"项目": "风险链冠军数", "值": len(shortlist)},
                {"项目": "读取历史价格收益", "值": True},
                {"项目": "用途", "值": "仅形成排序信号，不作为fresh OOS或准入结论"},
                {"项目": "配置/state/今日建议改变", "值": False},
            ]).to_excel(writer, sheet_name="摘要", index=False)
            shortlist.to_excel(writer, sheet_name="风险链冠军", index=False)
            competition.to_excel(writer, sheet_name="101只竞赛审计", index=False)
            scores.to_excel(writer, sheet_name="质量评分", index=False)
            coverage.to_excel(writer, sheet_name="质量覆盖", index=False)
            price_inventory.to_excel(writer, sheet_name="价格缓存覆盖", index=False)
        os.replace(temporary, workbook)
    finally:
        if temporary.exists():
            temporary.unlink()
    artifacts["workbook"] = {
        "path": workbook.as_posix(), "rows": None, "sha256": file_sha256(workbook)
    }
    manifest = {
        "schema_version": 1,
        "manifest_type": "ndx_v11_current_competition",
        "generated_at": utc_now_iso(),
        "status": "RESEARCH_SHORTLIST_ONLY_NOT_ADMITTED",
        **common,
        "selection_date": args.selection_date,
        "lookback_days": args.lookback_days,
        "attack_score_contract": {
            "ret_3y_rank_weight": 0.55,
            "ret_1y_rank_weight": 0.25,
            "drawdown_rank_weight": 0.12,
            "volatility_rank_weight": 0.08,
            "strict_price_rule": "Close date < selection_date",
        },
        "quality_input": factor_version,
        "taxonomy_input": taxonomy_version,
        "valuation_input": valuation_version,
        "quality_eligible_count": int(scores["quality_eligible"].sum()),
        "competition_eligible_count": int(competition["competition_eligible"].sum()),
        "shortlist_count": len(shortlist),
        "candidate_admission_count": 0,
        "valuation_overpay_guard_ready": True,
        "valuation_weight": 0.10,
        "valuation_weight_source": "price_weight_only",
        "valuation_cheap_reward_allowed": False,
        "artifacts": artifacts,
    }
    atomic_write_text(output / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="NDX v11当前质量与风险链内竞争（只读研究）")
    parser.add_argument("--factors", default="data/cache/research/ndx_v11_current_fundamental_evidence_v1/quality_factor_inputs.csv")
    parser.add_argument("--taxonomy", default="data/cache/candidate_pools/ndx_taxonomy_v2/current_review_20260713/reviewed/evidence_reviewed.csv")
    parser.add_argument("--valuation-scores", default="data/cache/research/ndx_v11_current_valuation_guard_v1/valuation_scores.csv")
    parser.add_argument("--price-cache-dir", default="data/cache")
    parser.add_argument("--output-dir", default="data/cache/research/ndx_v11_current_competition_v1")
    parser.add_argument("--selection-date", default="2026-07-13")
    parser.add_argument("--lookback-days", type=int, default=756)
    args = parser.parse_args()
    if args.lookback_days < 252:
        parser.error("--lookback-days must be at least 252")
    try:
        manifest = build_bundle(args)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"NDX当前竞赛失败: {exc}", file=sys.stderr)
        return 2
    print(
        "NDX当前竞赛完成 | "
        f"quality={manifest['quality_eligible_count']} | "
        f"eligible={manifest['competition_eligible_count']} | "
        f"chains={manifest['shortlist_count']} | admitted=0"
    )
    print(f"Manifest: {_resolve(args.output_dir) / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
