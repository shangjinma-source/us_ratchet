"""Generate the read-only NDX style/crowding diagnostic bundle."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.ndx_style_crowding import (  # noqa: E402
    DEFAULT_LOOKBACK_DAYS,
    plan_style_crowding_diagnostic,
    run_style_crowding_diagnostic,
    write_style_crowding_bundle,
)
from core.config import load_config  # noqa: E402


def _resolve(path: str | Path) -> Path:
    value = Path(path)
    return value if value.is_absolute() else ROOT / value


def main() -> int:
    parser = argparse.ArgumentParser(
        description="NDX当前8只/v8g/v10风险链、风格与拥挤度只读诊断"
    )
    parser.add_argument("--config", default="config/config.yaml")
    parser.add_argument(
        "--v8g-dir",
        default="data/cache/research/ndx_lab/ndx_incumbent_composition_sensitivity_v8g",
    )
    parser.add_argument(
        "--v10-dir",
        default="data/cache/research/ndx_lab/ndx_incumbent_fcf_overpay_guard_v10",
    )
    parser.add_argument(
        "--taxonomy",
        default="data/cache/candidate_pools/ndx_taxonomy_v2/taxonomy_records.csv",
    )
    parser.add_argument(
        "--overlay-dir",
        default="data/cache/candidate_pools/ndx_taxonomy_v2/incumbent_overlay",
    )
    parser.add_argument(
        "--output-dir",
        default="data/cache/research/ndx_style_crowding_v1",
    )
    parser.add_argument("--lookback-days", default=",".join(map(str, DEFAULT_LOOKBACK_DAYS)))
    parser.add_argument("--min-observations", type=int, default=60)
    parser.add_argument("--selection-lookback-years", type=float, default=3.0)
    parser.add_argument("--trade-cost-bps", type=float, default=10.0)
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--no-xlsx", action="store_true")
    args = parser.parse_args()

    config_path = _resolve(args.config)
    cfg = load_config(config_path)
    lookbacks = [int(item.strip()) for item in args.lookback_days.replace(";", ",").split(",") if item.strip()]
    if not lookbacks or any(item <= 1 for item in lookbacks):
        raise SystemExit("--lookback-days must contain positive integers above 1")

    paths = {
        "v8g_dir": _resolve(args.v8g_dir),
        "v10_dir": _resolve(args.v10_dir),
        "taxonomy_path": _resolve(args.taxonomy),
        "overlay_dir": _resolve(args.overlay_dir),
    }
    if args.plan_only:
        plan = plan_style_crowding_diagnostic(
            cfg,
            **paths,
            lookback_years=args.selection_lookback_years,
            trade_cost_bps=args.trade_cost_bps,
        )
        print(
            "NDX风格/拥挤度诊断计划完成 | "
            f"portfolio={plan['portfolio_count']} | selection_date={plan['selection_date']} | "
            "price_data_read=False | promotion_allowed=False"
        )
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0

    frames, summary = run_style_crowding_diagnostic(
        cfg,
        **paths,
        lookback_days=lookbacks,
        min_observations=args.min_observations,
        lookback_years=args.selection_lookback_years,
        trade_cost_bps=args.trade_cost_bps,
    )
    output = _resolve(args.output_dir)
    payload = write_style_crowding_bundle(
        frames,
        summary,
        output,
        write_xlsx=not args.no_xlsx,
    )
    coverage = frames["coverage"].set_index("metric")["value"].to_dict()
    print(
        "NDX风格/拥挤度诊断完成 | "
        f"portfolio={payload['portfolio_count']} | "
        f"classified_rows={coverage.get('taxonomy_classified_ticker_rows', 0)} | "
        f"unclassified_rows={coverage.get('taxonomy_unclassified_or_conflict_rows', 0)} | "
        f"price_errors={coverage.get('price_series_error_count', 0)} | "
        "return_data_used_for_classification=False"
    )
    print(f"输出: {output}")
    print(f"Manifest: {output / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
