from __future__ import annotations

from datetime import timedelta
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import pandas as pd

from backtest import ndx_conditional_repair_benchmark as benchmark


ROOT = Path(__file__).resolve().parents[1]


class NdxConditionalRepairBenchmarkTests(unittest.TestCase):
    def test_canonical_plan_locks_same_calendar_and_two_reference_roles(self):
        plan = benchmark.build_conditional_repair_benchmark_plan(
            repository_root=ROOT
        )
        self.assertEqual(
            plan["session_window"],
            {
                "start": "2022-11-29",
                "end": "2024-05-31",
                "sessions": 378,
                "cadence_sessions": 21,
                "rebalance_count": 18,
            },
        )
        self.assertEqual(list(plan["original8"]["weights"]), list(benchmark.ORIGINAL8_TICKERS))
        self.assertEqual(
            plan["target_012922"]["alignment"],
            "BACKWARD_ASOF_ON_EACH_STOCK_SESSION_NO_FUTURE_VALUES",
        )
        self.assertFalse(plan["promotion_allowed"])

    def test_target_prefix_alignment_is_backward_only_and_hash_locked(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / benchmark.TARGET_NAV_RELATIVE
            path.parent.mkdir(parents=True)
            sessions = pd.bdate_range("2022-01-03", periods=378)
            missing = set(sessions[10:38])
            rows = ["Date,UnitNav,AccumNav,DailyPct,Close\n"]
            previous = sessions[0] - timedelta(days=3)
            rows.append(f"{previous.date().isoformat()},0.8,0.8,,0.8\n")
            for index, session in enumerate(sessions):
                if session in missing:
                    continue
                close = 0.8772 if index == 0 else 0.88 + index / 10_000
                rows.append(
                    f"{session.date().isoformat()},{close},{close},,{close}\n"
                )
            raw = "".join(rows).encode("utf-8")
            path.write_bytes(raw + b"2026-01-01,2,2,,2\n")
            locked = dict(benchmark.LOCKED_SOURCE_HASHES)
            locked["target_nav_historical_prefix"] = benchmark._sha256(raw)
            with (
                mock.patch.object(benchmark, "TARGET_NAV_PREFIX_BYTES", len(raw)),
                mock.patch.object(benchmark, "LOCKED_SOURCE_HASHES", locked),
                mock.patch.object(benchmark, "EXPECTED_SESSIONS", len(sessions)),
                mock.patch.object(benchmark, "WINDOW_START", sessions[0].date().isoformat()),
            ):
                aligned, descriptor, _ = benchmark._load_target_nav(root, sessions)
                self.assertTrue((aligned["source_date"] <= aligned["session_date"]).all())
                self.assertEqual(int((aligned["lag_days"] > 0).sum()), 28)
                self.assertEqual(float(aligned.iloc[0]["normalized_close"]), 1.0)
                self.assertTrue(descriptor["historical_bytes_recoverable"])
                self.assertTrue(descriptor["source_file_changed_from_historical_prefix"])
                changed = bytearray(path.read_bytes())
                changed[20] ^= 1
                path.write_bytes(bytes(changed))
                with self.assertRaisesRegex(
                    benchmark.NdxConditionalRepairBenchmarkError,
                    "prefix is unavailable",
                ):
                    benchmark._load_target_nav(root, sessions)

    def test_ohlcv_validation_rejects_missing_or_impossible_bars(self):
        valid = pd.DataFrame(
            [{
                "Date": "2024-01-02",
                "Open": 10.0,
                "High": 11.0,
                "Low": 9.0,
                "Close": 10.5,
                "Volume": 100.0,
            }]
        )
        benchmark._validated_ohlcv(valid, "TEST")
        missing = valid.drop(columns=["Low"])
        with self.assertRaisesRegex(
            benchmark.NdxConditionalRepairBenchmarkError, "schema changed"
        ):
            benchmark._validated_ohlcv(missing, "TEST")
        impossible = valid.copy()
        impossible.loc[0, "High"] = 8.0
        with self.assertRaisesRegex(
            benchmark.NdxConditionalRepairBenchmarkError, "OHLCV is invalid"
        ):
            benchmark._validated_ohlcv(impossible, "TEST")

    def test_rebuild_uses_18_fixed_dates_and_reports_initial_peak_drawdown(self):
        dates = pd.bdate_range("2022-11-29", periods=378)
        tickers = list(benchmark.ORIGINAL8_TICKERS)
        prices = pd.DataFrame(
            {
                ticker: [100.0 + index * 0.01 for index in range(len(dates))]
                for ticker in tickers
            },
            index=dates,
        )
        target = pd.DataFrame(
            {
                "session_date": dates,
                "source_date": dates,
                "close": [1.0] * len(dates),
                "normalized_close": [1.0] * len(dates),
                "lag_days": [0] * len(dates),
            }
        )
        weights = {ticker: 1.0 / len(tickers) for ticker in tickers}
        captured = {
            "plan": {
                "plan_fingerprint": "a" * 64,
                "original8": {"identity_evidence_limitation": "fixture"},
            },
            "prices": prices,
            "target": target,
            "weights": weights,
            "chains": {ticker: f"chain-{ticker}" for ticker in tickers},
        }
        result = benchmark._rebuild_report(captured)
        control = result["original8_execution_control"]
        self.assertEqual(control["summary"]["whole_lot_rebalance_count"], 18)
        self.assertEqual(len(control["rebalance_ledger"]), 18)
        self.assertIn(
            "corrected_drawdown_with_initial_capital_peak",
            control["daily_risk_audit"],
        )
        self.assertEqual(result["target_012922_reference"]["path_return"], 0.0)
        self.assertFalse(result["promotion_allowed"])
        self.assertFalse(result["admission_claimed"])

    def test_write_then_read_only_verify_rejects_resigned_report(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "data/cache/research/benchmark"
            report = {
                "plan": {"plan_fingerprint": "b" * 64},
                "status": "COMPLETE_RESEARCH_ONLY",
            }
            captured = {"captures": {}}
            with (
                mock.patch.object(benchmark, "_capture_inputs", return_value=captured),
                mock.patch.object(benchmark, "_rebuild_report", return_value=report),
            ):
                benchmark.write_conditional_repair_benchmark(
                    repository_root=root, output_root=output
                )
                run_dir = output / "runs" / ("b" * 64)
                before = {
                    name: (run_dir / name).read_bytes()
                    for name in ("report.json", "manifest.json")
                }
                verified = benchmark.verify_conditional_repair_benchmark(
                    repository_root=root, output_root=output
                )
                self.assertEqual(verified["status"], "VERIFIED_COMPLETE_RESEARCH_ONLY")
                self.assertEqual(
                    before,
                    {name: (run_dir / name).read_bytes() for name in before},
                )
                value = json.loads(before["report.json"].decode("utf-8"))
                value["status"] = "RESIGNED_TAMPER"
                tampered = benchmark._json_bytes(value)
                (run_dir / "report.json").write_bytes(tampered)
                with self.assertRaisesRegex(
                    benchmark.NdxConditionalRepairBenchmarkError,
                    "report does not rebuild",
                ):
                    benchmark.verify_conditional_repair_benchmark(
                        repository_root=root, output_root=output
                    )
                self.assertEqual((run_dir / "report.json").read_bytes(), tampered)

    def test_output_outside_research_namespace_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaisesRegex(
                benchmark.NdxConditionalRepairBenchmarkError,
                "outside research namespace",
            ):
                benchmark.write_conditional_repair_benchmark(
                    repository_root=root, output_root=root / "outside"
                )


if __name__ == "__main__":
    unittest.main()
