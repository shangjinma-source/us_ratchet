"""Synthetic economic and artifact attacks; no real research build is run."""
from contextlib import ExitStack
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from backtest import ndx_dynamic_repair_research_bundle as bundle

REAL_DERIVE_INPUTS = bundle.derive_inputs


class DynamicRepairBundleTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        dates = pd.bdate_range("2024-01-02", periods=3)
        self.opens = pd.DataFrame({ticker: [100., 101., 102.] for ticker in "ABCD"}, index=dates)
        self.closes = self.opens * 1.01
        schedule = [dict(decision_date="2024-01-01", execution_date="2024-01-02",
                         targets={ticker: dict(ticker=ticker, issuer_id="issuer:" + ticker,
                                              target_weight=.25) for ticker in "ABCD"})]
        arguments = dict(execution_prices=self.opens, require_separate_execution_prices=True,
                         require_next_session_execution=True, require_issuer_trace=True,
                         initial_cash_usd=25000., minimum_cash_buffer_usd=100.,
                         transaction_cost_bps=10., valuation_end_date="2024-01-04")
        summary, rebalances, trades, path = bundle.simulate_dynamic_security_id_whole_lot_path(
            self.closes, schedule, **arguments)
        old_summary = {key: value for key, value in summary.items() if key != "k_path"}
        old_summary["k_path"] = json.dumps(summary["k_path"])
        old_summary["trading_session_count"] = summary["path_trading_session_count"]
        lane = dict(schedule=schedule, risk_chains={"2024-01-01": {ticker: ticker for ticker in "ABCD"}},
                    old_traces={name: bundle.frame_text(frame) for name, frame in
                                zip(("rebalances", "trades", "path"), (rebalances, trades, path))},
                    old_summary_csv=bundle.frame_text(pd.DataFrame([old_summary])))
        self.lanes = {f"source/track/ROLE_{number}": copy.deepcopy(lane) for number in range(14)}
        self.captured = dict(version=bundle.VERSION, code_hashes={"test": "locked"}, sources={},
                             tickers=list("ABCD"), selected_provenance_counts={key: 1 for key in self.lanes},
                             candidate_loader_consumed_hashes={}, upstream_provenance_checked_at_capture_only=True)
        self.stack.enter_context(patch.object(bundle, "code_hashes", return_value={"test": "locked"}))
        self.stack.enter_context(patch.object(bundle, "capture", side_effect=lambda root: copy.deepcopy(self.captured)))
        self.stack.enter_context(patch.object(bundle, "derive_inputs", side_effect=lambda *args:
            ({"valuation_end": "2024-01-04"}, self.opens, self.closes, copy.deepcopy(self.lanes))))

    def build(self):
        return Path(bundle.build(self.root)["run_directory"])

    def resign_results(self, run, mutation):
        results = json.loads((run / "results.json").read_bytes())
        mutation(results)
        raw = bundle.json_bytes(results)
        (run / "results.json").write_bytes(raw)
        manifest = json.loads((run / "manifest.json").read_bytes())
        manifest["results_sha256"] = bundle.sha(raw)
        manifest["coverage"] = bundle.coverage(results)
        (run / "manifest.json").write_bytes(bundle.json_bytes(manifest))

    def test_build_verify_replays_fourteen_lanes(self):
        run = self.build()
        before = {path.name: path.read_bytes() for path in run.iterdir()}
        result = bundle.verify(self.root, run)
        self.assertEqual(result["status"], "VERIFIED_ARCHIVED_EXECUTION_REPLAY")
        self.assertEqual(result["coverage"]["lane_count"], 14)
        self.assertFalse(result["promotion_allowed"])
        self.assertEqual(before, {path.name: path.read_bytes() for path in run.iterdir()})

    def test_resigned_missing_lane_rejected(self):
        run = self.build()
        self.resign_results(run, lambda results: results.pop(next(iter(results))))
        with self.assertRaisesRegex(ValueError, "Economic replay or lane coverage"):
            bundle.verify(self.root, run)

    def test_resigned_fee_or_nav_rejected(self):
        run = self.build()
        def attack(results):
            row = results[next(iter(results))]
            row["result"]["summary"]["total_transaction_cost_usd"] += 1
            row["frames"]["path"] = row["frames"]["path"].replace("25000", "26000")
        self.resign_results(run, attack)
        with self.assertRaisesRegex(ValueError, "Economic replay"):
            bundle.verify(self.root, run)

    def test_resigned_schedule_and_risk_rejected(self):
        run = self.build()
        def attack(results):
            row = results[next(iter(results))]
            row["inputs"]["schedule"][0]["targets"]["A"]["target_weight"] = .4
            row["inputs"]["risk_chains"]["2024-01-01"]["A"] = "fabricated"
        self.resign_results(run, attack)
        with self.assertRaisesRegex(ValueError, "Economic replay"):
            bundle.verify(self.root, run)

    def test_resigned_eligibility_rejected(self):
        run = self.build()
        def attack(results):
            row = results[next(iter(results))]["result"]
            row["execution_eligible"] = not row["execution_eligible"]
        self.resign_results(run, attack)
        with self.assertRaisesRegex(ValueError, "Economic replay"):
            bundle.verify(self.root, run)

    def test_verify_does_not_write_even_when_damaged(self):
        run = self.build()
        (run / "results.json").write_bytes(b"{}"); before = {p.name: p.read_bytes() for p in run.iterdir()}
        with self.assertRaises(ValueError):
            bundle.verify(self.root, run)
        self.assertEqual(before, {p.name: p.read_bytes() for p in run.iterdir()})

    def test_immutable_existing_run_rejected(self):
        self.build()
        with self.assertRaisesRegex(ValueError, "Immutable run"):
            self.build()

    def test_same_run_lock_fails_closed(self):
        output = self.root / bundle.OUTPUT_RELATIVE
        output.mkdir(parents=True)
        fingerprint = bundle.sha(bundle.json_bytes(self.captured))
        with bundle.run_lock(output, fingerprint):
            with self.assertRaisesRegex(ValueError, "another replay"):
                self.build()

    def test_stale_lock_file_is_not_a_running_process(self):
        output = self.root / bundle.OUTPUT_RELATIVE
        output.mkdir(parents=True)
        fingerprint = bundle.sha(bundle.json_bytes(self.captured))
        (output / (fingerprint + ".lock")).write_text("old process", encoding="utf-8")
        self.assertTrue(self.build().exists())

    def test_false_capture_counts_rejected(self):
        self.captured["selected_provenance_counts"][next(iter(self.lanes))] = 9
        with self.assertRaisesRegex(ValueError, "Capture coverage"):
            self.build()

    def test_manifest_cannot_inject_status_or_admission(self):
        run = self.build()
        manifest = json.loads((run / "manifest.json").read_bytes())
        manifest.update(status="LIVE_APPROVED", admission_allowed=True)
        (run / "manifest.json").write_bytes(bundle.json_bytes(manifest))
        with self.assertRaisesRegex(ValueError, "Manifest schema"):
            bundle.verify(self.root, run)

    def test_archived_source_missing_or_hash_mutation_rejected(self):
        path = self.root / "source.json"
        path.write_bytes(b"{}")
        archive = bundle.CapturedSources()
        archive.read(path, bundle.sha(b"{}"))
        path.write_bytes(b"new canonical source")
        frozen = bundle.CapturedSources(archive.entries)
        self.assertEqual(frozen.read(path, bundle.sha(b"{}")), b"{}")
        with self.assertRaisesRegex(ValueError, "Source binding"):
            frozen.read(path, bundle.sha(b"forged"))
        with self.assertRaisesRegex(ValueError, "Missing archived"):
            frozen.read(self.root / "missing")

    def test_source_root_self_hash_is_not_authority(self):
        archive = bundle.CapturedSources()
        path = self.root / bundle.SOURCE_RELATIVE / "manifest.json"
        path.parent.mkdir(parents=True)
        path.write_bytes(b'{"self_hash":"resigned"}')
        with self.assertRaisesRegex(ValueError, "Source binding"):
            bundle.source_contract(self.root, archive)

    def test_price_panel_uses_archived_parsed_bytes_after_canonical_change(self):
        def write(name, raw):
            path = self.root / name
            path.write_bytes(raw)
            return dict(path=path.as_posix(), sha256=bundle.sha(raw))
        prices = write("prices.csv", b"Date,Open,Close\n2024-01-02,100,101\n2024-01-03,102,103\n")
        sidecar = write("prices.meta.json", b"{}")
        row = dict(ticker="A", status="FETCHED", rows=2, **prices,
                   sidecar_path=sidecar["path"], sidecar_sha256=sidecar["sha256"])
        inventory = write("inventory.csv", bundle.frame_text(pd.DataFrame([row])).encode())
        manifest = write("prices.manifest.json", bundle.json_bytes(dict(
            status="READY", manifest_type="ndx_cardinality_whole_lot_execution_price_bundle",
            artifacts={"inventory": inventory})))
        source = dict(inputs={"execution_price_manifest": manifest})
        archive = bundle.CapturedSources()
        expected = bundle.captured_prices(source, archive, ["A"])
        Path(prices["path"]).write_bytes(b"different canonical data")
        actual = bundle.captured_prices(source, bundle.CapturedSources(archive.entries), ["A"])
        for left, right in zip(expected, actual):
            pd.testing.assert_frame_equal(left, right, check_exact=True)

    def test_derived_schedule_has_explicit_iso_dates(self):
        coordinates = dict(source_batch="exact_v3", universe_track="track", policy_role="RETURN")
        rows = []
        for number, date in enumerate(pd.bdate_range("2024-01-02", periods=14)):
            rows.append(dict(selection_date=date.date().isoformat(),
                             decision_data_end=(date - pd.offsets.BDay(1)).date().isoformat(),
                             holding_count=4, portfolio_id=str(number), weight_spec="equal_weight",
                             tickers="A;B;C;D", security_ids="A;B;C;D", issuer_ids="IA;IB;IC;ID",
                             risk_chains="a;b;c;d", weights="A:.25;B:.25;C:.25;D:.25",
                             declared_constraints_passed=True, return_p50=.1, return_p10=.01,
                             max_drawdown_p50=.1, max_drawdown_p90=.2, target_012922_distance=.1))
        archive = bundle.CapturedSources()
        index_rows = []
        for name, raw in ([("selected_candidates", bundle.frame_text(pd.DataFrame(rows)).encode())]
            + [("whole_lot_" + name, text.encode()) for name, text
               in next(iter(self.lanes.values()))["old_traces"].items()]):
            path = self.root / (name + ".csv")
            path.write_bytes(raw)
            archive.read(path, bundle.sha(raw))
            index_rows.append(dict(name=name, path=path.as_posix(), sha256=bundle.sha(raw), **coordinates))
        index = pd.DataFrame(index_rows)
        with patch.object(bundle, "source_contract", return_value=(
                {}, index, index[index.name == "selected_candidates"], pd.DataFrame([coordinates]))), \
                patch.object(bundle, "captured_prices", return_value=(self.opens, self.closes)):
            _, _, _, lanes = REAL_DERIVE_INPUTS(self.root, archive, list("ABCD"))
        schedule = next(iter(lanes.values()))["schedule"]
        self.assertEqual(schedule[0]["decision_date"], "2024-01-01")
        self.assertEqual(schedule[0]["execution_date"], "2024-01-02")
        bundle.json_bytes(lanes)


if __name__ == "__main__":
    unittest.main()
