import os
import json
from pathlib import Path
from types import SimpleNamespace
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import pandas as pd

from backtest.fund_mirror import _available_report, _history_with_availability
from data import fund_holdings, funds
from data.versioning import (
    ensure_dataset_manifest,
    file_sha256,
    modeled_availability_manifest,
    write_dataset_manifest,
)


class FundDataVersioningTests(unittest.TestCase):
    def test_complete_nav_api_refresh_parses_all_pages(self):
        class Response:
            status_code = 200

            def __init__(self, date, nav, page):
                self.text = json.dumps({
                    "Data": {"LSJZList": [{
                        "FSRQ": date, "DWJZ": nav, "LJJZ": nav,
                        "JZZZL": "1.25",
                    }]},
                    "ErrCode": 0, "TotalCount": 2,
                    "PageSize": 1, "PageIndex": page,
                })

        class Session:
            def get(self, *args, **kwargs):
                page = kwargs["params"]["pageIndex"]
                return Response(
                    "2026-01-02" if page == 1 else "2026-01-01",
                    "1.1" if page == 1 else "1.0",
                    page,
                )

        cfg = SimpleNamespace(
            cache_dir="unused",
            data=SimpleNamespace(proxy="", start_date=None, end_date=None),
        )
        with patch("requests.Session", return_value=Session()), patch.object(
            funds, "_write_cache", return_value={"version_id": "test"}
        ) as write_cache:
            frame, meta = funds._fetch_eastmoney_fund_nav("012922", cfg)

        self.assertEqual(list(frame.index.strftime("%Y-%m-%d")), ["2026-01-01", "2026-01-02"])
        self.assertEqual(meta.source, "eastmoney_fund_api")
        self.assertAlmostEqual(frame.loc["2026-01-02", "DailyPct"], 0.0125)
        self.assertEqual(write_cache.call_args.kwargs["source_record_count"], 2)
        self.assertEqual(write_cache.call_args.kwargs["source_page_count"], 2)

    def test_source_confirmed_empty_holdings_year_is_not_a_fetch_error(self):
        response = SimpleNamespace(
            status_code=200,
            text='var apidata={ content:"",arryear:[2026,2025,2024,2023,2022],curyear:2021};',
        )
        cfg = SimpleNamespace(
            cache_dir="unused",
            data=SimpleNamespace(proxy=""),
        )
        with patch("requests.get", return_value=response):
            frame, meta = fund_holdings._fetch_eastmoney_holdings_year(
                "012922", cfg, 2021
            )

        self.assertTrue(frame.empty)
        self.assertEqual(meta.rows, 0)
        self.assertTrue(meta.manifest["empty_year_confirmed"])
        self.assertEqual(meta.manifest["available_years"], [2026, 2025, 2024, 2023, 2022])

    def test_partial_nav_refresh_never_writes_cache(self):
        class Response:
            def __init__(self, status_code, text=""):
                self.status_code = status_code
                self.text = text

        class Session:
            def __init__(self):
                self.calls = 0

            def get(self, *args, **kwargs):
                self.calls += 1
                if self.calls == 1:
                    return Response(
                        200,
                        json.dumps({
                            "Data": {"LSJZList": [{
                                "FSRQ": "2026-01-02", "DWJZ": "1.0",
                                "LJJZ": "1.0", "JZZZL": "0.0",
                            }]},
                            "ErrCode": 0, "TotalCount": 2,
                            "PageSize": 1, "PageIndex": 1,
                        }),
                    )
                return Response(500)

        cfg = SimpleNamespace(
            cache_dir="unused",
            data=SimpleNamespace(proxy="", start_date=None, end_date=None),
        )
        with patch("requests.Session", return_value=Session()), patch.object(
            funds, "_write_cache"
        ) as write_cache:
            with self.assertRaises(funds.FundDataError):
                funds._fetch_eastmoney_fund_nav("012922", cfg)
            write_cache.assert_not_called()

    def test_partial_holdings_refresh_keeps_complete_history_cache(self):
        with TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            history_dir = cache_dir / "fund_holdings"
            history_dir.mkdir(parents=True)
            (history_dir / "012922_history.csv").write_text(
                "report_date,rank,ticker,secid,fund_name,asset_class\n"
                "2022-12-31,1,TSM,105.TSM,test,US\n",
                encoding="utf-8",
            )
            cfg = SimpleNamespace(
                cache_dir=str(cache_dir),
                data=SimpleNamespace(start_date="2022-01-01"),
            )
            fetched = pd.DataFrame({
                "report_date": ["2022-12-31"],
                "rank": [1],
                "ticker": ["TSM"],
                "secid": ["105.TSM"],
            })
            fetched_meta = fund_holdings.FundHoldingMeta(
                code="012922",
                source="test",
                rows=1,
                manifest={"report_versions": ["report-v1"]},
            )

            def fetch_year(code, config, year, **kwargs):
                if year == 2022:
                    return fetched, fetched_meta
                raise fund_holdings.FundHoldingError("simulated 2023 failure")

            with patch.object(
                fund_holdings, "_fetch_eastmoney_holdings_year", side_effect=fetch_year
            ), patch.object(fund_holdings, "_write_history_cache") as write_history:
                history, meta = fund_holdings.get_fund_holding_history(
                    "012922", cfg, start_year=2022, end_year=2023
                )

            self.assertEqual(len(history), 1)
            self.assertEqual(meta.source, "fund_holdings_history_cache_stale")
            self.assertIn("2023", meta.errors)
            write_history.assert_not_called()

    def test_content_hash_changes_dataset_version(self):
        with TemporaryDirectory() as tmp:
            cache = Path(tmp) / "012922.csv"
            cache.write_text("Date,Close\n2026-01-01,1.0\n", encoding="utf-8")
            first = write_dataset_manifest(
                cache,
                dataset_type="fund_nav",
                dataset_key="012922",
                source="test_source",
                fetched_at="2026-01-02T00:00:00+00:00",
                row_count=1,
                data_start="2026-01-01",
                data_end="2026-01-01",
            )
            cache.write_text("Date,Close\n2026-01-01,1.1\n", encoding="utf-8")
            second = write_dataset_manifest(
                cache,
                dataset_type="fund_nav",
                dataset_key="012922",
                source="test_source",
                fetched_at="2026-01-03T00:00:00+00:00",
                row_count=1,
                data_start="2026-01-01",
                data_end="2026-01-01",
            )

            self.assertNotEqual(first["version_id"], second["version_id"])
            self.assertEqual(second["content_sha256"], file_sha256(cache))

    def test_legacy_cache_uses_file_mtime_as_limited_evidence(self):
        with TemporaryDirectory() as tmp:
            cache = Path(tmp) / "012922_history.csv"
            cache.write_text("report_date,ticker\n2025-12-31,TSM\n", encoding="utf-8")
            legacy_ts = 1_767_225_600  # 2026-01-01T00:00:00Z
            os.utime(cache, (legacy_ts, legacy_ts))

            manifest = ensure_dataset_manifest(
                cache,
                dataset_type="fund_holdings_history",
                dataset_key="012922",
                row_count=1,
                data_start="2025-12-31",
                data_end="2025-12-31",
                legacy_source="legacy_fund_holdings_history_cache",
            )

            self.assertTrue(manifest["legacy_backfill"])
            self.assertEqual(manifest["fetched_at_evidence"], "legacy_file_mtime")
            self.assertFalse(manifest["publication_time_known"])
            self.assertEqual(manifest["source_confidence"], "cache_file_only")

    def test_manifest_identity_mismatch_is_never_reused(self):
        with TemporaryDirectory() as tmp:
            cache = Path(tmp) / "012922.csv"
            cache.write_text("Date,Close\n2026-01-01,1.0\n", encoding="utf-8")
            write_dataset_manifest(
                cache,
                dataset_type="fund_nav",
                dataset_key="wrong-fund",
                source="test_source",
                row_count=1,
            )

            manifest = ensure_dataset_manifest(
                cache,
                dataset_type="fund_nav",
                dataset_key="012922",
                row_count=1,
            )

            self.assertEqual(manifest["dataset_key"], "012922")
            self.assertEqual(manifest["manifest_rebuild_reason"], "manifest_identity_mismatch")
            self.assertTrue(manifest["legacy_backfill"])

    def test_availability_guard_never_selects_future_report(self):
        history = pd.DataFrame({
            "report_date": ["2024-03-31", "2024-06-30"],
            "ticker": ["A", "B"],
        })
        guarded = _history_with_availability(history, 30)

        report, _ = _available_report(guarded, pd.Timestamp("2024-07-29"))
        self.assertEqual(report, "2024-03-31")
        report, selected = _available_report(guarded, pd.Timestamp("2024-07-30"))
        self.assertEqual(report, "2024-06-30")
        self.assertEqual(selected["available_date"].iloc[0], "2024-07-30")

        policy = modeled_availability_manifest(history["report_date"], 0)
        self.assertTrue(policy["zero_delay_upper_bound_only"])
        self.assertEqual(policy["availability_date_kind"], "modeled_not_source_publication_date")


if __name__ == "__main__":
    unittest.main()
