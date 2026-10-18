import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import pandas as pd

from backtest.fund_style import (
    _industry_report,
    _price_version,
    _region_and_concentration,
    _series_metrics,
)
from data import fund_style


class FundStyleTests(unittest.TestCase):
    def test_asset_table_parser_uses_reported_fields(self):
        html = """
        <table><tr><th>other</th></tr><tr><td>x</td></tr></table>
        <table>
          <tr><th>报告期</th><th>股票占净比</th><th>债券占净比</th>
              <th>现金占净比</th><th>存托凭证占净比</th><th>净资产（亿元）</th></tr>
          <tr><td>2026-03-31</td><td>74.67%</td><td>---</td>
              <td>16.27%</td><td>10.08%</td><td>98.66</td></tr>
        </table>
        """
        frame = fund_style._parse_asset_table(html)

        self.assertEqual(len(frame), 1)
        self.assertAlmostEqual(frame.iloc[0]["stock_weight"], 0.7467)
        self.assertAlmostEqual(frame.iloc[0]["cash_weight"], 0.1627)
        self.assertAlmostEqual(frame.iloc[0]["depositary_receipt_weight"], 0.1008)
        self.assertTrue(pd.isna(frame.iloc[0]["bond_weight"]))

    def test_incomplete_turnover_response_never_writes_cache(self):
        response = SimpleNamespace(
            status_code=200,
            json=lambda: {
                "ErrCode": 0,
                "TotalCount": 2,
                "Data": [{"REPORTDATE": "2025-12-31", "STOCKTURNOVER": 380.84}],
            },
        )
        cfg = SimpleNamespace(data=SimpleNamespace(proxy=""), cache_dir="unused")
        with patch("requests.get", return_value=response), patch.object(
            fund_style, "_write_cache"
        ) as write_cache:
            with self.assertRaises(fund_style.FundStyleDataError):
                fund_style._fetch_turnover("012922", cfg)
            write_cache.assert_not_called()

    def test_region_report_never_extrapolates_partial_disclosure(self):
        history = pd.DataFrame({
            "report_date": ["2025-12-31"] * 3 + ["2026-03-31"] * 2,
            "rank": [1, 2, 3, 1, 2],
            "secid": ["106.A", "0.B", "116.C", "106.D", "0.E"],
            "asset_class": ["US", "CN_A", "HK", "US", "CN_A"],
            "nav_weight": [0.4, 0.3, 0.2, 0.3, 0.2],
        })
        region, concentration = _region_and_concentration(
            history,
            {"2025-12-31": 0.9, "2026-03-31": 0.9},
        )

        self.assertEqual(region["latest_disclosure"]["scope"], "partial_holdings")
        self.assertEqual(region["latest_expanded"]["report_date"], "2025-12-31")
        self.assertAlmostEqual(region["latest_expanded"]["disclosure_coverage"], 1.0)
        self.assertIsNone(concentration["latest"]["disclosed_hhi"])

    def test_industry_weights_cross_check_official_equity(self):
        frame = pd.DataFrame({
            "report_date": ["2026-03-31", "2026-03-31"],
            "sector_code": ["45", "20"],
            "sector": ["信息技术", "工业"],
            "nav_weight": [0.70, 0.15],
        })
        report = _industry_report(frame, {"2026-03-31": 0.85})

        self.assertTrue(report["asset_cross_check"]["passed"])
        self.assertAlmostEqual(report["latest"]["sector_hhi"], (0.70 / 0.85) ** 2 + (0.15 / 0.85) ** 2)

    def test_performance_metrics_are_serializable_and_flow_free(self):
        dates = pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"])
        metrics = _series_metrics(pd.Series([100.0, 80.0, 120.0], index=dates))

        self.assertAlmostEqual(metrics["total_return"], 0.2)
        self.assertAlmostEqual(metrics["max_drawdown"], 0.2)
        json.dumps(metrics, allow_nan=False)

    def test_benchmark_version_only_hashes_used_range(self):
        meta = SimpleNamespace(source="test", cached=True)
        used = pd.Series(
            [100.0, 101.0],
            index=pd.to_datetime(["2026-01-01", "2026-01-02"]),
        )
        with_unused_future = pd.concat([
            used,
            pd.Series([999.0], index=pd.to_datetime(["2026-01-03"])),
        ])

        first = _price_version("QQQ", used, meta)
        second = _price_version(
            "QQQ",
            with_unused_future,
            meta,
            used_start="2026-01-01",
            used_end="2026-01-02",
        )

        self.assertEqual(first["version_id"], second["version_id"])


if __name__ == "__main__":
    unittest.main()
