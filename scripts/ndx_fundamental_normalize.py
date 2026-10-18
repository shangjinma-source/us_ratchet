"""Normalize cached SEC Company Facts into point-in-time quality inputs."""
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

from core.config import load_config
from core.helpers import atomic_write_text
from data.ndx_fundamental_normalization import (
    NORMALIZATION_POLICY_ID,
    NormalizationPolicy,
    build_quality_factor_inputs,
    normalize_point_in_time_facts,
)
from data.ndx_fundamentals import fundamental_cache_dir, raw_bundle_sha256
from data.versioning import (
    file_sha256,
    manifest_path,
    utc_now_iso,
    write_dataset_manifest,
)


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


def _verified_manifest(path: Path) -> dict:
    target = manifest_path(path)
    if not path.exists() or not target.exists():
        raise FileNotFoundError(f"versioned readiness input missing: {path}")
    payload = json.loads(target.read_text(encoding="utf-8"))
    if payload.get("content_sha256") != file_sha256(path):
        raise ValueError(f"readiness input hash mismatch: {path}")
    return payload


def _finite_float(value) -> float | None:
    number = float(value)
    return number if np.isfinite(number) else None


def _minimum_coverage(frame: pd.DataFrame, key: str) -> dict[str, float | None]:
    return {
        str(name): _finite_float(group["coverage"].min())
        for name, group in frame.groupby(key)
    }


def _integrity_failures(
    values: pd.DataFrame,
    components: pd.DataFrame,
) -> pd.DataFrame:
    rows = []
    for row in values[~values["arithmetic_passed"]].itertuples(index=False):
        rows.append({
            "failure_type": "normalization_arithmetic",
            "selection_date": row.selection_date,
            "ticker": row.ticker,
            "cik": row.cik,
            "metric": row.metric,
            "detail": row.normalization_method,
        })
    for row in values[~values["future_data_guard_passed"]].itertuples(index=False):
        rows.append({
            "failure_type": "future_data_guard",
            "selection_date": row.selection_date,
            "ticker": row.ticker,
            "cik": row.cik,
            "metric": row.metric,
            "detail": row.source_available_date_max,
        })
    if not components.empty:
        mismatched = components[
            components["unit"].ne(components["normalized_unit"])
        ]
        for row in mismatched.itertuples(index=False):
            rows.append({
                "failure_type": "component_unit_mismatch",
                "selection_date": row.selection_date,
                "ticker": None,
                "cik": row.cik,
                "metric": row.metric,
                "detail": f"{row.unit}!={row.normalized_unit}",
            })
        future = components[
            components["available_date"].gt(components["selection_date"])
            | components["period_end"].ge(components["selection_date"])
        ]
        for row in future.itertuples(index=False):
            rows.append({
                "failure_type": "component_future_data_guard",
                "selection_date": row.selection_date,
                "ticker": None,
                "cik": row.cik,
                "metric": row.metric,
                "detail": f"available={row.available_date};period_end={row.period_end}",
            })
    columns = [
        "failure_type",
        "selection_date",
        "ticker",
        "cik",
        "metric",
        "detail",
    ]
    return pd.DataFrame(rows, columns=columns)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Normalize SEC Company Facts at historical NDX selection dates; "
            "never rank or admit securities."
        )
    )
    parser.add_argument("--config", default="config/config.yaml")
    parser.add_argument("--input-dir", default="")
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--high-confidence-age-days", type=int, default=200)
    parser.add_argument("--maximum-age-days", type=int, default=550)
    args = parser.parse_args()

    cfg = load_config(_resolve(args.config))
    source = (
        _resolve(args.input_dir)
        if args.input_dir else fundamental_cache_dir(cfg)
    )
    output = (
        _resolve(args.output_dir)
        if args.output_dir else source / "normalization_v1"
    )
    output.mkdir(parents=True, exist_ok=True)

    readiness_path = source / "readiness_summary.json"
    if not readiness_path.exists():
        raise FileNotFoundError(readiness_path)
    readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
    if int(readiness.get("cached_companyfacts") or 0) != int(
        readiness.get("mapped_ciks") or -1
    ):
        raise ValueError("Company Facts cache is incomplete")
    if readiness.get("future_data_guard_passed") is not True:
        raise ValueError("readiness future-data guard did not pass")

    input_paths = {
        "crosswalk": source / "cik_crosswalk.csv",
        "raw_index": source / "raw_index.csv",
        "fact_availability": source / "fact_availability.csv",
    }
    input_manifests = {
        key: _verified_manifest(path)
        for key, path in input_paths.items()
    }
    plan_path = source / "plan.csv"
    if not plan_path.exists():
        raise FileNotFoundError(plan_path)
    plan = pd.read_csv(plan_path)
    raw_index = pd.read_csv(input_paths["raw_index"])
    observed_bundle_hash = raw_bundle_sha256(raw_index)
    if observed_bundle_hash != readiness.get("raw_bundle_sha256"):
        raise ValueError("raw Company Facts bundle hash changed after readiness")
    records = pd.read_csv(
        input_paths["fact_availability"],
        low_memory=False,
    )

    policy = NormalizationPolicy(
        high_confidence_age_days=int(args.high_confidence_age_days),
        maximum_age_days=int(args.maximum_age_days),
    )
    print("\nNDX point-in-time fundamental normalization")
    print(
        f"Policy: {NORMALIZATION_POLICY_ID} | raw CIKs: {len(raw_index)} | "
        f"fact rows: {len(records)} | selection rows: {len(plan)}"
    )
    values, components, normalization_summary = normalize_point_in_time_facts(
        plan,
        records,
        policy=policy,
    )
    factor_inputs, factor_coverage = build_quality_factor_inputs(values)
    failures = _integrity_failures(values, components)

    files = {
        "normalized_values": (values, "normalized_values.csv"),
        "normalization_components": (components, "normalization_components.csv"),
        "normalization_summary": (
            normalization_summary,
            "normalization_summary.csv",
        ),
        "quality_factor_inputs": (factor_inputs, "quality_factor_inputs.csv"),
        "factor_coverage": (factor_coverage, "factor_coverage.csv"),
        "integrity_failures": (failures, "integrity_failures.csv"),
    }
    for frame, filename in files.values():
        _atomic_csv(frame, output / filename)

    common_extra = {
        "normalization_policy_id": NORMALIZATION_POLICY_ID,
        "raw_bundle_sha256": observed_bundle_hash,
        "plan_sha256": file_sha256(plan_path),
        "high_confidence_age_days": policy.high_confidence_age_days,
        "maximum_age_days": policy.maximum_age_days,
        "future_data_guard": "source available_date <= selection_date and period_end < selection_date",
        "scoring_allowed": False,
    }
    evidence = {}
    for key, (frame, filename) in files.items():
        path = output / filename
        manifest = write_dataset_manifest(
            path,
            dataset_type=f"ndx_fundamental_{key}",
            dataset_key=NORMALIZATION_POLICY_ID,
            source="sec_companyfacts_normalized",
            source_locator="https://data.sec.gov/api/xbrl/companyfacts/",
            row_count=len(frame),
            data_start=str(plan["selection_date"].min())[:10],
            data_end=str(plan["selection_date"].max())[:10],
            extra=common_extra,
        )
        evidence[key] = {
            "filename": filename,
            "rows": len(frame),
            "sha256": manifest["content_sha256"],
        }

    workbook = output / "ndx_fundamental_normalization.xlsx"
    temporary = workbook.with_name(workbook.stem + ".tmp.xlsx")
    try:
        with pd.ExcelWriter(temporary, engine="openpyxl") as writer:
            normalization_summary.to_excel(
                writer, sheet_name="normalization_summary", index=False
            )
            factor_coverage.to_excel(
                writer, sheet_name="factor_coverage", index=False
            )
            factor_inputs.to_excel(
                writer, sheet_name="quality_factor_inputs", index=False
            )
            values.to_excel(writer, sheet_name="normalized_values", index=False)
            components.to_excel(
                writer, sheet_name="source_components", index=False
            )
            failures.to_excel(writer, sheet_name="integrity_failures", index=False)
        os.replace(temporary, workbook)
    finally:
        if temporary.exists():
            temporary.unlink()

    usable = values[values["usable"]]
    normalized_metric_min = {
        str(metric): _finite_float(group["normalized_coverage"].min())
        for metric, group in normalization_summary.groupby("metric")
    }
    factor_min = _minimum_coverage(factor_coverage, "factor")
    payload = {
        "generated_at": utc_now_iso(),
        "research_only": True,
        "normalization_policy_id": NORMALIZATION_POLICY_ID,
        "policy": policy.__dict__,
        "raw_bundle_sha256": observed_bundle_hash,
        "source_versions": {
            key: manifest.get("version_id")
            for key, manifest in input_manifests.items()
        },
        "plan_sha256": file_sha256(plan_path),
        "selection_dates": int(plan["selection_date"].nunique()),
        "universe_rows": int(
            plan.drop_duplicates(["selection_date", "ticker"]).shape[0]
        ),
        "normalized_rows": len(values),
        "usable_rows": len(usable),
        "component_rows": len(components),
        "integrity_failure_rows": len(failures),
        "normalization_integrity_passed": failures.empty,
        "minimum_normalized_coverage_by_metric": normalized_metric_min,
        "minimum_factor_coverage": factor_min,
        "scoring_allowed": False,
        "scoring_blockers": [
            "point_in_time_sector_classification_not_ready",
            "debt_aggregation_policy_pending",
            "shares_fx_and_valuation_policy_pending",
            "factor_winsorization_and_missingness_policy_not_frozen",
            "training_backtest_not_run",
        ],
        "files": {
            **{key: item["filename"] for key, item in evidence.items()},
            "workbook": workbook.name,
        },
    }
    atomic_write_text(
        output / "normalization_readiness.json",
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
    )
    manifest_payload = {
        "schema_version": 1,
        "generated_at": payload["generated_at"],
        "normalization_policy_id": NORMALIZATION_POLICY_ID,
        "raw_bundle_sha256": observed_bundle_hash,
        "plan_sha256": payload["plan_sha256"],
        "source_versions": payload["source_versions"],
        "evidence_files": evidence,
        "normalization_integrity_passed": failures.empty,
        "scoring_allowed": False,
    }
    atomic_write_text(
        output / "manifest.json",
        json.dumps(
            manifest_payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ) + "\n",
    )
    print(
        f"Normalized: {len(usable)}/{len(values)} metric rows | "
        f"components: {len(components)} | integrity failures: {len(failures)}"
    )
    print("Scoring remains disabled until the declared blockers are resolved.")
    print(f"Workbook: {workbook}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
