"""Real daily economics must survive adversarial self-consistent re-signing."""
import json
from pathlib import Path
import unittest

from backtest import ndx_dynamic_shadow_daily_v2 as integrity
from backtest.ndx_dynamic_shadow_daily import canonical_sha256
from data.versioning import file_sha256
import test_ndx_dynamic_shadow_daily_v4_execution_e2e as execution_fixture


def _resign(value, field):
    value.pop(field, None)
    value[field] = canonical_sha256(value)


def _write_json(path, value):
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


class DailyEconomicReplayTests(unittest.TestCase):
    def test_nominal_source_mode_and_integer_rows_are_strict(self):
        def check(root, manifest):
            from backtest import ndx_dynamic_shadow_daily_economic_replay as replay
            path = Path(manifest["research_artifacts"]["nominal_price_evidence_manifest"]["path"])
            original = path.read_bytes()
            _, _, sessions = replay.calendar.load_reviewed_calendar_projection(
                root / replay.calendar.CALENDAR_RELATIVE, repository_root=root)
            for field, invalid in (("source_mode", "adjusted_prices"), ("rows", 3.0)):
                with self.subTest(field=field):
                    value = json.loads(original)
                    ticker = value["tickers"][0]
                    if field == "rows":
                        invalid = float(value["sources"][ticker]["rows"])
                    value["sources"][ticker][field] = invalid
                    _resign(value, "manifest_sha256")
                    _write_json(path, value)
                    try:
                        with self.assertRaises(ValueError):
                            replay._nominal(path, root, sessions, value["tickers"], replay._ReadSet())
                    finally:
                        path.write_bytes(original)
        execution_fixture.Daily4ExecutionE2ETests().exercise(after_first=check, verify_restart=False)

    def test_real_eleven_economic_lanes_pass(self):
        def check(root, manifest):
            from backtest.ndx_dynamic_shadow_daily_economic_replay import verify_daily_economic_replay
            self.assertEqual(manifest["independent_lane_count"], 10)
            self.assertEqual(manifest["original_8_control_rows"], 1)
            proof = verify_daily_economic_replay(manifest, repository_root=root)
            self.assertIs(proof["economic_replay_verified"], True)
            self.assertEqual(proof["economic_lane_count"], 11)
        execution_fixture.Daily4ExecutionE2ETests().exercise(after_first=check, verify_restart=False)

    def test_self_consistent_selector_total_value_forgery_rejected(self):
        def check(root, manifest):
            artifacts = manifest["research_artifacts"]
            selector = "strict_technology__return__v1"
            descriptor = artifacts["selector_lane_ledgers"][selector]
            ledger = Path(descriptor["path"])
            rows = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
            rows[-1]["path_state"]["total_value_usd"] += 100000
            _resign(rows[-1], "record_sha256")
            ledger.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
            descriptor["sha256"] = file_sha256(ledger)
            alignment_path = Path(artifacts["three_way_alignment_manifest"]["path"])
            alignment = json.loads(alignment_path.read_text(encoding="utf-8"))
            alignment["selector_lane_prefixes"][selector]["terminal_record_sha256"] = rows[-1]["record_sha256"]
            _resign(alignment, "manifest_sha256")
            _write_json(alignment_path, alignment)
            for binding in (manifest["three_way_alignment_manifest"], artifacts["three_way_alignment_manifest"]):
                binding["sha256"] = file_sha256(alignment_path)
            _resign(manifest, "run_manifest_sha256")
            run_path = root / "data/cache/research/ndx_dynamic_shadow_daily_v1/latest_run.json"
            _write_json(run_path, manifest)
            # This is the verified gap: all former integrity checks still pass.
            integrity.verify_daily_run_manifest(run_path, repository_root=None)
            from backtest.ndx_dynamic_shadow_daily_economic_replay import verify_daily_economic_replay
            with self.assertRaises(ValueError):
                verify_daily_economic_replay(manifest, repository_root=root)
            from backtest.ndx_dynamic_shadow_daily_v3 import verify_daily_run_manifest
            with self.assertRaisesRegex(ValueError, "economic path differs"):
                verify_daily_run_manifest(run_path, repository_root=root)
        execution_fixture.Daily4ExecutionE2ETests().exercise(after_first=check, verify_restart=False)


if __name__ == "__main__":
    unittest.main()
