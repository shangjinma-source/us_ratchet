"""Inspect or refresh versioned fund research datasets.

PowerShell / PyCharm examples:
    python scripts\fund_data_manifest.py --fund 012922
    python scripts\fund_data_manifest.py --fund 012922 --refresh
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.config import load_config
from data.fund_holdings import get_fund_holding_history
from data.funds import get_fund_nav
from data.versioning import data_version_payload, modeled_availability_manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect version manifests for fund research data")
    parser.add_argument("--config", default="config/config.yaml")
    parser.add_argument("--fund", default="012922")
    parser.add_argument("--start-year", type=int, default=2022)
    parser.add_argument("--end-year", type=int, default=0)
    parser.add_argument("--availability-delay-days", type=int, default=30)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    cfg = load_config(args.config)
    nav, nav_meta = get_fund_nav(
        args.fund,
        cfg,
        local_only=not args.refresh,
        refresh=args.refresh,
    )
    holdings, holdings_meta = get_fund_holding_history(
        args.fund,
        cfg,
        start_year=args.start_year,
        end_year=args.end_year or None,
        local_only=not args.refresh,
    )
    report_dates = sorted({str(value)[:10] for value in holdings["report_date"].dropna()})
    refresh_succeeded = bool(
        args.refresh
        and not nav_meta.cached
        and not holdings_meta.cached
        and not nav_meta.errors
        and not holdings_meta.errors
    )
    payload = {
        "fund_code": args.fund,
        "refresh_requested": bool(args.refresh),
        "refresh_succeeded": refresh_succeeded,
        "refreshed": refresh_succeeded,
        "nav": data_version_payload(
            nav_meta,
            used_rows=len(nav),
            used_start=nav.index[0].strftime("%Y-%m-%d"),
            used_end=nav.index[-1].strftime("%Y-%m-%d"),
        ),
        "holdings_history": data_version_payload(
            holdings_meta,
            used_rows=len(holdings),
            used_report_start=report_dates[0] if report_dates else None,
            used_report_end=report_dates[-1] if report_dates else None,
            used_report_count=len(report_dates),
        ),
        "availability": modeled_availability_manifest(
            report_dates, args.availability_delay_days
        ),
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(
            f"fund={args.fund} refresh_requested={payload['refresh_requested']} "
            f"refresh_succeeded={payload['refresh_succeeded']}"
        )
        for key in ("nav", "holdings_history"):
            item = payload[key]
            print(
                f"{key}: version={item.get('version_id') or '-'} "
                f"source={item.get('source') or '-'} fetched_at={item.get('fetched_at') or '-'} "
                f"evidence={item.get('fetched_at_evidence') or '-'} "
                f"completeness={item.get('completeness') or '-'}"
            )
        availability = payload["availability"]
        print(
            f"availability: report_date + {availability['availability_delay_days']} calendar days; "
            f"reports={availability['report_count']}; kind={availability['availability_date_kind']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
