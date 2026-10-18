from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from data.ndx_price_basis import (
    NdxPriceBasisError,
    PriceBasisPolicy,
    crosscheck_share_split_events,
    fetch_unadjusted_bars,
    load_verified_unadjusted_cache,
    normalize_unadjusted_bars,
    point_in_time_raw_price_rows,
    raw_split_events,
    write_unadjusted_cache,
)


def bars(values: list[tuple[str, float]]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Date": date,
                "Open": close,
                "High": close * 1.01,
                "Low": close * 0.99,
                "Close": close,
                "Volume": 1000,
            }
            for date, close in values
        ]
    )


class NdxPriceBasisTests(unittest.TestCase):
    def test_fetch_eastmoney_explicitly_requests_unadjusted_prices(self):
        source_rows = [
            {
                "date": "2024-06-07",
                "open": 1200,
                "high": 1210,
                "low": 1190,
                "close": 1208,
                "volume": 1,
            }
        ]
        with patch(
            "data.ndx_price_basis.cn_source.fetch_eastmoney_kline",
            return_value=source_rows,
        ) as fetch:
            frame, mode, errors = fetch_unadjusted_bars(
                "NVDA",
                begin="2024-06-01",
                end="2024-06-10",
                source_chain=["eastmoney"],
            )
        self.assertEqual(mode, "eastmoney_fqt_0")
        self.assertEqual(errors, {})
        self.assertEqual(float(frame.iloc[0]["Close"]), 1208)
        self.assertEqual(fetch.call_args.kwargs["fqt"], 0)

    def test_normalization_rejects_invalid_ohlc_ordering(self):
        invalid = bars([("2024-01-02", 100)])
        invalid.loc[0, "High"] = 90
        with self.assertRaisesRegex(NdxPriceBasisError, "OHLC ordering"):
            normalize_unadjusted_bars(invalid, ticker="TEST")

    def test_fetch_validates_only_the_requested_research_interval(self):
        source_rows = [
            {
                "date": "2010-01-04",
                "open": 100,
                "high": 90,
                "low": 80,
                "close": 100,
                "volume": 1,
            },
            {
                "date": "2024-01-02",
                "open": 100,
                "high": 101,
                "low": 99,
                "close": 100,
                "volume": 1,
            },
        ]
        with patch(
            "data.ndx_price_basis.cn_source.fetch_sina_daily",
            return_value=source_rows,
        ):
            frame, mode, errors = fetch_unadjusted_bars(
                "TEST",
                begin="2024-01-01",
                end="2024-01-03",
                source_chain=["sina"],
            )
        self.assertEqual(mode, "sina_raw_daily")
        self.assertEqual(errors, {})
        self.assertEqual(list(frame.index.strftime("%Y-%m-%d")), ["2024-01-02"])

    def test_versioned_cache_rejects_content_tampering(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            frame = normalize_unadjusted_bars(
                bars([("2024-01-02", 100), ("2024-01-03", 101)]),
                ticker="TEST",
            )
            write_unadjusted_cache(
                directory,
                "TEST",
                frame,
                source_mode="eastmoney_fqt_0",
                requested_begin="2024-01-01",
                requested_end="2024-01-04",
            )
            loaded, manifest = load_verified_unadjusted_cache(
                directory,
                "TEST",
                requested_begin="2024-01-01",
                requested_end="2024-01-04",
            )
            self.assertEqual(len(loaded), 2)
            self.assertEqual(manifest["price_basis"], "unadjusted_nominal_trade_price")
            cache = directory / "raw" / "TEST.csv"
            cache.write_text(cache.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            with self.assertRaisesRegex(NdxPriceBasisError, "content_sha256"):
                load_verified_unadjusted_cache(
                    directory,
                    "TEST",
                    requested_begin="2024-01-01",
                    requested_end="2024-01-04",
                )

    def test_point_in_time_row_uses_raw_close_strictly_before_selection(self):
        raw = normalize_unadjusted_bars(
            bars([
                ("2024-01-02", 200),
                ("2024-01-03", 210),
            ]),
            ticker="TEST",
        )
        adjusted = normalize_unadjusted_bars(
            bars([
                ("2024-01-02", 100),
                ("2024-01-03", 105),
            ]),
            ticker="TEST",
        )
        plan = pd.DataFrame([{"selection_date": "2024-01-03", "ticker": "TEST"}])
        manifests = {
            "TEST": {
                "price_basis": "unadjusted_nominal_trade_price",
                "corporate_action_adjustment": "none",
                "source": "eastmoney",
                "source_request_mode": "eastmoney_fqt_0",
                "source_semantics_evidence": "explicit_unadjusted_request_parameter",
                "version_id": "raw:test",
                "content_sha256": "abc",
            }
        }
        result = point_in_time_raw_price_rows(
            plan,
            {"TEST": raw},
            manifests,
            adjusted_series={"TEST": adjusted},
            policy=PriceBasisPolicy(maximum_price_age_days=7),
        ).iloc[0]
        self.assertEqual(result["price_date"], "2024-01-02")
        self.assertEqual(float(result["price"]), 200)
        self.assertEqual(float(result["adjusted_to_raw_ratio"]), 0.5)
        self.assertTrue(bool(result["price_ready"]))

    def test_point_in_time_row_uses_lifecycle_price_ticker_but_keeps_identity(self):
        raw = normalize_unadjusted_bars(
            bars([("2022-06-07", 194.25)]),
            ticker="FB",
        )
        plan = pd.DataFrame([{
            "selection_date": "2022-06-08",
            "ticker": "META",
            "price_ticker": "FB",
            "ticker_alias_applied": True,
            "ticker_lifecycle_rule_id": "meta_fb_to_meta_2022",
        }])
        manifests = {
            "FB": {
                "price_basis": "unadjusted_nominal_trade_price",
                "corporate_action_adjustment": "none",
                "source": "sina",
                "source_request_mode": "sina_raw_daily",
                "source_semantics_evidence": (
                    "provider_raw_response_plus_split_crosscheck"
                ),
                "version_id": "raw:fb",
                "content_sha256": "abc",
            }
        }
        result = point_in_time_raw_price_rows(
            plan,
            {"FB": raw},
            manifests,
        ).iloc[0]
        self.assertEqual(result["ticker"], "META")
        self.assertEqual(result["price_ticker"], "FB")
        self.assertEqual(result["price"], 194.25)
        self.assertTrue(bool(result["ticker_alias_applied"]))
        self.assertTrue(bool(result["price_ready"]))

    def test_share_split_crosscheck_matches_raw_price_direction(self):
        raw = normalize_unadjusted_bars(
            bars([
                ("2022-06-30", 100),
                ("2022-07-01", 25),
                ("2022-07-05", 26),
            ]),
            ticker="TEST",
        )
        price_events = raw_split_events(
            {"TEST": raw},
            policy=PriceBasisPolicy(split_ratio_tolerance=0.08),
        )
        share_events = pd.DataFrame([
            {
                "ticker": "TEST",
                "prior_selection_date": "2022-06-01",
                "selection_date": "2022-08-01",
                "nearest_split_ratio": 4,
                "split_like": True,
            }
        ])
        result = crosscheck_share_split_events(
            share_events,
            price_events,
            policy=PriceBasisPolicy(split_ratio_tolerance=0.08),
        ).iloc[0]
        self.assertEqual(result["matched_raw_event_date"], "2022-07-01")
        self.assertEqual(result["matched_raw_split_factor"], 4)
        self.assertEqual(result["crosscheck_status"], "matched")


if __name__ == "__main__":
    unittest.main()
