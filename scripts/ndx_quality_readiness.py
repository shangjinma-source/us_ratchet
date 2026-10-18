"""Build a white-box NDX quality-score readiness report without returns."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.ndx_quality import (
    QUALITY_POLICY_ID,
    QualityPolicy,
    build_quality_scores,
    quality_selection_previews,
)
from core.config import load_config
from core.helpers import atomic_write_text
from data.ndx_fundamentals import fundamental_cache_dir
from data.versioning import file_sha256, utc_now_iso, write_dataset_manifest


MIN_SCORE_COVERAGE = 0.85


def _resolve(path: str | Path) -> Path:
    value = Path(path)
    return value if value.is_absolute() else ROOT / value


def _atomic_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    try:
        frame.to_csv(temporary, index=False, encoding="utf-8-sig")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _verified_evidence(
    directory: Path,
    key: str,
    *,
    required_flags: tuple[str, ...],
) -> tuple[dict, Path]:
    manifest_path = directory / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for flag in required_flags:
        if manifest.get(flag) is not True:
            raise ValueError(f"upstream evidence flag did not pass: {flag}")
    evidence = (manifest.get("evidence_files") or {}).get(key) or {}
    path = directory / str(evidence.get("filename") or "")
    if (
        not path.exists()
        or not evidence.get("sha256")
        or file_sha256(path) != evidence["sha256"]
    ):
        raise ValueError(f"upstream evidence hash mismatch: {key}")
    return manifest, path


def _selection_stability(previews: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for mode, group in previews.groupby("mode"):
        by_date = {
            date: set(frame["ticker"].astype(str))
            for date, frame in group.groupby("selection_date")
        }
        dates = sorted(by_date)
        for previous, current in zip(dates, dates[1:]):
            old = by_date[previous]
            new = by_date[current]
            union = old | new
            rows.append({
                "mode": mode,
                "previous_date": previous,
                "selection_date": current,
                "retained_count": len(old & new),
                "entered_count": len(new - old),
                "exited_count": len(old - new),
                "jaccard": len(old & new) / len(union) if union else 1.0,
            })
    return pd.DataFrame(rows)


def _gate_failures(
    scores: pd.DataFrame,
    coverage: pd.DataFrame,
    concentration: pd.DataFrame,
    policy: QualityPolicy,
) -> pd.DataFrame:
    rows = []
    for row in coverage[
        coverage["score_coverage"].lt(MIN_SCORE_COVERAGE)
    ].itertuples(index=False):
        rows.append({
            "failure_type": "score_coverage",
            "selection_date": row.selection_date,
            "ticker": None,
            "detail": f"{row.score_coverage:.6f}<{MIN_SCORE_COVERAGE:.6f}",
        })
    invalid_scores = scores[
        scores["quality_eligible"]
        & (
            ~np.isfinite(pd.to_numeric(scores["quality_score"], errors="coerce"))
            | scores["quality_score"].lt(0)
            | scores["quality_score"].gt(100)
        )
    ]
    for row in invalid_scores.itertuples(index=False):
        rows.append({
            "failure_type": "quality_score_bounds",
            "selection_date": row.selection_date,
            "ticker": row.ticker,
            "detail": row.quality_score,
        })
    for row in concentration[
        concentration["constrained_unique_sic4"].lt(
            int(np.ceil(policy.preview_top_n / policy.max_names_per_sic4))
        )
        | concentration["constrained_unique_sic2"].lt(
            int(np.ceil(policy.preview_top_n / policy.max_names_per_sic2))
        )
    ].itertuples(index=False):
        rows.append({
            "failure_type": "constrained_sic_diversity",
            "selection_date": row.selection_date,
            "ticker": None,
            "detail": (
                f"sic4={row.constrained_unique_sic4};"
                f"sic2={row.constrained_unique_sic2}"
            ),
        })
    return pd.DataFrame(
        rows,
        columns=["failure_type", "selection_date", "ticker", "detail"],
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Construct point-in-time SEC quality scores and SIC-constrained "
            "selection previews without reading returns."
        )
    )
    parser.add_argument("--config", default="config/config.yaml")
    parser.add_argument("--normalization-dir", default="")
    parser.add_argument("--sic-dir", default="")
    parser.add_argument("--output-dir", default="")
    args = parser.parse_args()

    cfg = load_config(_resolve(args.config))
    fundamental_dir = fundamental_cache_dir(cfg)
    normalization_dir = (
        _resolve(args.normalization_dir)
        if args.normalization_dir else fundamental_dir / "normalization_v1"
    )
    sic_dir = (
        _resolve(args.sic_dir)
        if args.sic_dir else fundamental_dir / "sic_history_v1"
    )
    output = (
        _resolve(args.output_dir)
        if args.output_dir else fundamental_dir / "quality_v1"
    )
    output.mkdir(parents=True, exist_ok=True)

    normalization_manifest, factor_path = _verified_evidence(
        normalization_dir,
        "quality_factor_inputs",
        required_flags=("normalization_integrity_passed",),
    )
    sic_manifest, sic_path = _verified_evidence(
        sic_dir,
        "selection_sic",
        required_flags=("sic_evidence_complete", "future_data_guard_passed"),
    )
    factor_inputs = pd.read_csv(factor_path, low_memory=False)
    sic_evidence = pd.read_csv(
        sic_path,
        low_memory=False,
        dtype={"sic_group_2d": str},
    )
    policy = QualityPolicy()
    scores, factor_audit, coverage = build_quality_scores(
        factor_inputs,
        sic_evidence,
        policy=policy,
    )
    previews, rejections, concentration = quality_selection_previews(
        scores,
        policy=policy,
    )
    stability = _selection_stability(previews)
    failures = _gate_failures(scores, coverage, concentration, policy)

    print("\nNDX point-in-time quality-score readiness")
    print(
        f"Policy: {QUALITY_POLICY_ID} | dates: {scores['selection_date'].nunique()} | "
        f"rows: {len(scores)} | minimum coverage: "
        f"{coverage['score_coverage'].min() * 100:.2f}%"
    )
    output_frames = {
        "quality_scores": scores,
        "factor_audit": factor_audit,
        "score_coverage": coverage,
        "selection_previews": previews,
        "selection_rejections": rejections,
        "concentration_audit": concentration,
        "selection_stability": stability,
        "gate_failures": failures,
    }
    for name, frame in output_frames.items():
        _atomic_csv(frame, output / f"{name}.csv")

    upstream = {
        "normalization_manifest_sha256": file_sha256(
            normalization_dir / "manifest.json"
        ),
        "normalization_factor_sha256": normalization_manifest[
            "evidence_files"
        ]["quality_factor_inputs"]["sha256"],
        "sic_manifest_sha256": file_sha256(sic_dir / "manifest.json"),
        "sic_selection_sha256": sic_manifest["evidence_files"][
            "selection_sic"
        ]["sha256"],
    }
    common_extra = {
        "quality_policy_id": QUALITY_POLICY_ID,
        **upstream,
        "return_data_read": False,
        "live_scoring_allowed": False,
    }
    evidence = {}
    for name, frame in output_frames.items():
        path = output / f"{name}.csv"
        manifest = write_dataset_manifest(
            path,
            dataset_type=f"ndx_quality_{name}",
            dataset_key=QUALITY_POLICY_ID,
            source="sec_companyfacts_plus_historical_sic",
            source_locator="https://data.sec.gov/api/xbrl/companyfacts/",
            row_count=len(frame),
            data_start=str(scores["selection_date"].min())[:10],
            data_end=str(scores["selection_date"].max())[:10],
            extra=common_extra,
        )
        evidence[name] = {
            "filename": path.name,
            "rows": len(frame),
            "sha256": manifest["content_sha256"],
        }

    workbook = output / "ndx_quality_readiness.xlsx"
    temporary = workbook.with_name(workbook.stem + ".tmp.xlsx")
    try:
        with pd.ExcelWriter(temporary, engine="openpyxl") as writer:
            coverage.to_excel(writer, sheet_name="score_coverage", index=False)
            concentration.to_excel(
                writer, sheet_name="concentration_audit", index=False
            )
            previews.to_excel(writer, sheet_name="selection_previews", index=False)
            rejections.to_excel(writer, sheet_name="selection_rejections", index=False)
            stability.to_excel(writer, sheet_name="selection_stability", index=False)
            scores.to_excel(writer, sheet_name="quality_scores", index=False)
            factor_audit.to_excel(writer, sheet_name="factor_audit", index=False)
            failures.to_excel(writer, sheet_name="gate_failures", index=False)
        os.replace(temporary, workbook)
    finally:
        if temporary.exists():
            temporary.unlink()

    violation = (
        ~concentration["unconstrained_sic4_cap_passed"]
        | ~concentration["unconstrained_sic2_cap_passed"]
    )
    payload = {
        "generated_at": utc_now_iso(),
        "research_only": True,
        "quality_policy_id": QUALITY_POLICY_ID,
        "policy": policy.__dict__,
        "selection_dates": int(scores["selection_date"].nunique()),
        "score_rows": len(scores),
        "minimum_score_coverage": float(coverage["score_coverage"].min()),
        "median_score_coverage": float(coverage["score_coverage"].median()),
        "unconstrained_sic_violation_dates": int(violation.sum()),
        "unconstrained_sic_violation_rate": float(violation.mean()),
        "constrained_minimum_unique_sic4": int(
            concentration["constrained_unique_sic4"].min()
        ),
        "constrained_minimum_unique_sic2": int(
            concentration["constrained_unique_sic2"].min()
        ),
        "median_constrained_jaccard": float(
            stability.loc[
                stability["mode"].eq("sic_constrained"), "jaccard"
            ].median()
        ),
        "gate_failure_rows": len(failures),
        "research_ranking_ready": failures.empty,
        "return_data_read": False,
        "training_backtest_run": False,
        "live_scoring_allowed": False,
        "excluded_from_primary_score": {
            "net_margin": "one_time_gain_sensitivity",
            "research_and_development_intensity": "industry_dependent_missingness",
        },
        "files": {
            **{name: item["filename"] for name, item in evidence.items()},
            "workbook": workbook.name,
        },
    }
    atomic_write_text(
        output / "quality_readiness.json",
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
    )
    atomic_write_text(
        output / "manifest.json",
        json.dumps({
            "schema_version": 1,
            "generated_at": payload["generated_at"],
            "quality_policy_id": QUALITY_POLICY_ID,
            **upstream,
            "evidence_files": evidence,
            "research_ranking_ready": failures.empty,
            "return_data_read": False,
            "training_backtest_run": False,
            "live_scoring_allowed": False,
        }, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    print(
        f"Unconstrained SIC violations: {int(violation.sum())}/"
        f"{len(concentration)} | gate failures: {len(failures)}"
    )
    print("No return data was read; no training or live promotion occurred.")
    print(f"Workbook: {workbook}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
