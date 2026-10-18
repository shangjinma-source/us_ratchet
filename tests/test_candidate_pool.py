from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import json
import unittest
from unittest.mock import patch

import pandas as pd

from data import candidate_pool


def _ndx_html(count: int) -> str:
    rows = "".join(
        f"<tr><td>T{i:03d}</td><td>Company {i}</td></tr>" for i in range(count)
    )
    return (
        "<html><head><title>Nasdaq-100 Companies</title></head><body>"
        "<table><tr><th>Symbol</th><th>Company Name</th></tr>"
        f"{rows}</table></body></html>"
    )


def _ndx_json_ld(count: int) -> str:
    payload = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "ItemList",
                "@id": "https://www.nasdaq.com/products/global-indexes/nasdaq-100/companies#itemlist",
                "name": "Nasdaq-100 Company Breakdown",
                "itemListElement": [
                    {
                        "@type": "ListItem",
                        "position": index + 1,
                        "name": f"Company {index}",
                        "description": f"T{index:03d}",
                    }
                    for index in range(count)
                ],
            }
        ],
    }
    return (
        "<html><head><title>Nasdaq-100 Companies</title>"
        f"<script data-source='schema' type='application/ld+json'>{json.dumps(payload)}</script>"
        "</head><body></body></html>"
    )


def _ndx_json_ld_with_missing_descriptions(count: int, missing: set[int]) -> str:
    parser = candidate_pool._JsonLdParser()
    parser.feed(_ndx_json_ld(count))
    payload = json.loads(parser.documents[0])
    for index in missing:
        payload["@graph"][0]["itemListElement"][index].pop("description", None)
    return (
        "<html><head><title>Nasdaq-100 Companies</title>"
        f"<script type='application/ld+json'>{json.dumps(payload)}</script>"
        "</head><body></body></html>"
    )


def _snapshot_row(ticker: str, name: str, *, as_of: str = "2026-07-10") -> dict:
    return {
        "as_of_date": as_of,
        "source_type": "index_constituent",
        "source_id": "nasdaq_100",
        "ticker": ticker,
        "name": name,
        "weight": None,
        "sector": "",
        "source_locator": candidate_pool.NASDAQ_NDX_COMPANIES_URL,
    }


def _cfg(cache_dir: Path, tickers=("NVDA", "TSM")):
    return SimpleNamespace(
        cache_dir=cache_dir,
        data=SimpleNamespace(proxy=None),
        symbols=[SimpleNamespace(ticker=ticker, cap_total=1000.0) for ticker in tickers],
        execution=SimpleNamespace(venue="HSBC"),
    )


class CandidatePoolTests(unittest.TestCase):
    def test_official_ndx_parser_accepts_complete_unique_security_list(self):
        frame = candidate_pool.parse_nasdaq_ndx_companies(
            _ndx_html(101), as_of_date="2026-07-10"
        )
        self.assertEqual(len(frame), 101)
        self.assertEqual(frame["ticker"].nunique(), 101)
        self.assertTrue(frame["weight"].isna().all())

    def test_official_ndx_parser_accepts_current_json_ld_item_list(self):
        frame = candidate_pool.parse_nasdaq_ndx_companies(
            _ndx_json_ld(101), as_of_date="2026-09-05"
        )
        self.assertEqual(len(frame), 101)
        self.assertEqual(frame["ticker"].nunique(), 101)
        self.assertEqual(frame.iloc[0]["source_id"], "nasdaq_100")

    def test_json_ld_missing_tickers_require_exact_unique_prior_name_match(self):
        known = {f"COMPANY {index}": f"T{index:03d}" for index in (2, 77)}
        frame = candidate_pool.parse_nasdaq_ndx_companies(
            _ndx_json_ld_with_missing_descriptions(101, {2, 77}),
            as_of_date="2026-09-05",
            known_name_to_ticker=known,
        )
        self.assertEqual(len(frame), 101)
        self.assertEqual(
            {row["ticker"] for row in frame.attrs["ticker_name_fallbacks"]},
            {"T002", "T077"},
        )

    def test_json_ld_missing_ticker_without_prior_match_fails_closed(self):
        with self.assertRaisesRegex(candidate_pool.CandidatePoolError, "ItemList|count"):
            candidate_pool.parse_nasdaq_ndx_companies(
                _ndx_json_ld_with_missing_descriptions(101, {2, 77}),
                as_of_date="2026-09-05",
            )

    def test_incomplete_ndx_response_is_rejected(self):
        with self.assertRaisesRegex(candidate_pool.CandidatePoolError, "count"):
            candidate_pool.parse_nasdaq_ndx_companies(
                _ndx_html(99), as_of_date="2026-07-10"
            )

    def test_incomplete_refresh_never_overwrites_last_complete_snapshot(self):
        with TemporaryDirectory() as tmp:
            cfg = _cfg(Path(tmp))
            complete = candidate_pool.parse_nasdaq_ndx_companies(
                _ndx_html(101), as_of_date="2026-07-09"
            )
            candidate_pool._write_snapshot(
                cfg,
                complete,
                source_id="nasdaq_100",
                source_type="index_constituent",
                source="test",
                source_locator=candidate_pool.NASDAQ_NDX_COMPANIES_URL,
                fetched_at="2026-07-09T12:00:00+00:00",
                completeness="test_complete",
                as_of_date_evidence="test",
                source_effective_date_known=False,
            )
            current = candidate_pool._current_path(cfg, "nasdaq_100")
            before = candidate_pool.file_sha256(current)

            with patch.object(
                candidate_pool,
                "_fetch_nasdaq_html",
                return_value=(_ndx_html(99), "2026-07-10T12:00:00+00:00"),
            ):
                frame, meta = candidate_pool.refresh_nasdaq_100_snapshot(cfg)

            self.assertEqual(len(frame), 101)
            self.assertTrue(meta.stale)
            self.assertIn("refresh", meta.errors)
            self.assertEqual(candidate_pool.file_sha256(current), before)

    def test_current_snapshot_manifest_is_blocked_from_historical_backtest(self):
        with self.assertRaisesRegex(candidate_pool.CandidatePoolError, "point-in-time"):
            candidate_pool.assert_historical_backtest_allowed({
                "historical_backtest_allowed": False,
                "point_in_time_scope": "current_snapshot_only",
            })

    def test_qqq_export_requires_complete_weighted_equity_list(self):
        lines = ["Invesco QQQ Holdings as of 07/09/2026", "Ticker,Company,% TNA"]
        lines.extend(
            f"Q{i:03d},Company {i},1.00%" for i in range(100)
        )
        frame = candidate_pool.parse_invesco_qqq_export(
            ("\n".join(lines) + "\n").encode("utf-8")
        )
        self.assertEqual(len(frame), 100)
        self.assertAlmostEqual(float(frame["weight"].sum()), 1.0)
        self.assertEqual(frame["as_of_date"].iloc[0], "2026-07-09")

    def test_registry_keeps_all_ndx_as_control_without_guessing_weights(self):
        with TemporaryDirectory() as tmp:
            cfg = _cfg(Path(tmp))
            dates = pd.bdate_range(end="2026-07-09", periods=504)
            price = pd.DataFrame({
                "Date": [value.strftime("%Y-%m-%d") for value in dates],
                "Close": [100.0 + i for i in range(504)],
            })
            price.to_csv(Path(tmp) / "NVDA.csv", index=False)
            price.to_csv(Path(tmp) / "QQQ.csv", index=False)
            ndx = pd.DataFrame([
                _snapshot_row("NVDA", "NVIDIA Corp"),
                _snapshot_row("UNKN", "Unclassified Company"),
            ])
            meta = candidate_pool.CandidatePoolMeta(
                source_id="nasdaq_100",
                source="test",
                rows=2,
                as_of_date="2026-07-10",
                cached=True,
                manifest={
                    "version_id": "ndx:test",
                    "observed_added": [],
                    "observed_removed": [],
                    "historical_backtest_allowed": False,
                },
            )
            payload = candidate_pool.build_security_candidate_registry(cfg, ndx, meta)
            by_ticker = {row["ticker"]: row for row in payload["candidates"]}

            self.assertIn("all_ndx_control", by_ticker["UNKN"]["scopes"])
            self.assertEqual(by_ticker["UNKN"]["stage"], "screening_pending")
            self.assertIsNone(by_ticker["NVDA"]["qqq_weight"])
            self.assertTrue(by_ticker["NVDA"]["current_screen"]["eligible"])
            self.assertFalse(by_ticker["NVDA"]["historical_backtest"]["eligible"])
            self.assertFalse(by_ticker["NVDA"]["live"]["eligible"])
            self.assertEqual(by_ticker["NVDA"]["sell_policy"], "no_automatic_sell")

    def test_stale_price_cache_is_not_current_screen_ready(self):
        with TemporaryDirectory() as tmp:
            cfg = _cfg(Path(tmp), tickers=("NVDA",))
            stale_dates = pd.bdate_range(end="2026-06-26", periods=504)
            market_dates = pd.bdate_range(end="2026-07-09", periods=504)
            for ticker, dates in (("NVDA", stale_dates), ("QQQ", market_dates)):
                pd.DataFrame({
                    "Date": [value.strftime("%Y-%m-%d") for value in dates],
                    "Close": range(1, 505),
                }).to_csv(Path(tmp) / f"{ticker}.csv", index=False)
            ndx = pd.DataFrame([_snapshot_row("NVDA", "NVIDIA Corp")])
            meta = candidate_pool.CandidatePoolMeta(
                source_id="nasdaq_100",
                source="test",
                rows=1,
                as_of_date="2026-07-10",
                cached=True,
                manifest={"version_id": "ndx:test"},
            )

            payload = candidate_pool.build_security_candidate_registry(cfg, ndx, meta)
            nvda = next(row for row in payload["candidates"] if row["ticker"] == "NVDA")

            self.assertEqual(nvda["price_history"]["status"], "stale")
            self.assertGreater(nvda["price_history"]["lag_business_days"], 3)
            self.assertFalse(nvda["current_screen"]["eligible"])

    def test_observed_ndx_removal_freezes_incumbent_new_capital_not_sell(self):
        with TemporaryDirectory() as tmp:
            cfg = _cfg(Path(tmp), tickers=("NVDA",))
            ndx = pd.DataFrame([_snapshot_row("AMD", "Advanced Micro Devices")])
            meta = candidate_pool.CandidatePoolMeta(
                source_id="nasdaq_100",
                source="test",
                rows=1,
                as_of_date="2026-07-10",
                cached=True,
                manifest={
                    "version_id": "ndx:test",
                    "observed_added": [],
                    "observed_removed": ["NVDA"],
                    "historical_backtest_allowed": False,
                },
            )
            payload = candidate_pool.build_security_candidate_registry(cfg, ndx, meta)
            nvda = next(row for row in payload["candidates"] if row["ticker"] == "NVDA")

            self.assertEqual(nvda["stage"], "frozen_review")
            self.assertEqual(
                nvda["new_capital_policy"], "freeze_new_capital_pending_review"
            )
            self.assertEqual(nvda["sell_policy"], "no_automatic_sell")
            self.assertEqual(nvda["today_advice_impact"], "none")


if __name__ == "__main__":
    unittest.main()
