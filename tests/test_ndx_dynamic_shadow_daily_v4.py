"""Adapter branch tests; mocked stages are not full daily/activation E2E."""
from contextlib import nullcontext
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import ndx_dynamic_shadow_daily_v4 as adapter


class Daily4AdapterTests(unittest.TestCase):
    def test_round_trip_reader_preserves_frozen_decimal_value(self):
        value = 99.61862398195003
        raw = adapter.engine.pd.DataFrame({"Open": [value], "Close": [value]}).to_csv(index=False)
        parsed = adapter._RoundTripPriceCsv(adapter.engine.pd).read_csv(StringIO(raw))
        self.assertEqual(parsed.iloc[0]["Open"], value)
        self.assertEqual(parsed.to_csv(index=False), raw)

    def test_nominal_reader_is_module_local_and_restored_on_failure(self):
        original = adapter.engine.pd
        seen = []
        def failing_nominal(*args, **kwargs):
            seen.append(adapter.engine.pd)
            self.assertIsNot(adapter.engine.pd, original)
            self.assertIs(adapter.engine.pd._pandas, original)
            raise RuntimeError("nominal failure")
        with patch.object(adapter.engine, "_nominal_price_evidence", side_effect=failing_nominal):
            callback = adapter._adapter_bindings()["_nominal_price_evidence"]
            with self.assertRaisesRegex(RuntimeError, "nominal failure"):
                callback([], None, valuation_end_date="2026-10-02")
        self.assertEqual(len(seen), 1)
        self.assertIs(adapter.engine.pd, original)

    def test_commands_use_new_generations_and_budgeted_controller(self):
        command = adapter._generator_command("2026-10-01")
        self.assertEqual(command[:3], [adapter.sys.executable, "-B", str(adapter.GENERATOR_SCRIPT)])
        for option in ("--seal", "--refresh-official", "--refresh-membership", "--rebuild-taxonomy"):
            self.assertIn(option, command)
        command = adapter._fresh_command("2026-10-01", max_jobs=1)
        self.assertEqual(command[:4], [adapter.sys.executable, "-B", str(adapter.FRESH_SCRIPT), "--execute"])
        self.assertNotIn("--max-jobs", command)

    def test_input_verify_uses_public_candidate3_command(self):
        with patch.object(adapter.previous, "_run_checked") as runner:
            adapter._verify_input_seal("2026-10-01")
        command = runner.call_args.args[0]
        self.assertEqual(command[2:4], [str(adapter.GENERATOR_SCRIPT), "--verify"])

    def test_missing_activation_blocks_before_refresh(self):
        # Import failure itself is tested, not a substituted activation validator.
        with patch.dict("sys.modules", {"backtest.ndx_dynamic_shadow_activation_v5": None}), \
                patch.object(adapter.engine, "single_instance_lock", return_value=nullcontext()), \
                patch.object(adapter.engine, "_protected_hashes", return_value={}), \
                patch.object(adapter.previous, "_refresh_calendar") as refresh, \
                patch.object(adapter.engine, "execute") as execute:
            with self.assertRaises(ModuleNotFoundError):
                adapter.execute()
            refresh.assert_not_called()
            execute.assert_not_called()

    def test_all_consumers_require_acceptance_and_recheck_after(self):
        for name in ("verify_final_candidate_snapshot", "verify_final_role_seal_record", "build_realized_lane_decisions"):
            with self.subTest(name=name), patch.object(adapter.engine, name, return_value="old result") as consumer:
                bindings = adapter._adapter_bindings()
                with patch.object(adapter, "verify_accepted_final", side_effect=ValueError("missing receipt")):
                    with self.assertRaisesRegex(ValueError, "missing receipt"):
                        bindings[name]("final")
                consumer.assert_not_called()
                with patch.object(adapter, "verify_accepted_final", side_effect=[{"proof": 1}, {"proof": 2}]):
                    with self.assertRaisesRegex(adapter.NdxDynamicShadowDailyError, "changed during final consumption"):
                        bindings[name]("final")
                self.assertEqual(consumer.call_count, 1)

    def test_guard_preserves_original_call_result_and_arguments(self):
        with patch.object(adapter.engine, "verify_final_role_seal_record", return_value={"old": True}) as verifier:
            guarded = adapter._adapter_bindings()["verify_final_role_seal_record"]
            with patch.object(adapter, "verify_accepted_final", return_value={"same": True}) as acceptance:
                self.assertEqual(guarded("final", "ledger", expected_final_root="root"), {"old": True})
            verifier.assert_called_once_with("final", "ledger", expected_final_root="root")
            self.assertEqual(acceptance.call_count, 2)

    def test_realize_returns_cumulative_not_current_run_count(self):
        with patch.object(adapter.engine, "_realize_ready_decisions", return_value=0) as realize:
            callback = adapter._adapter_bindings()["_realize_ready_decisions"]
            with patch.object(adapter, "verified_realized_batch_count", side_effect=[3, 3]) as count:
                self.assertEqual(callback("sessions"), 3)
            realize.assert_called_once_with("sessions")
            self.assertEqual(count.call_count, 2)

    def test_realize_rejects_invalid_existing_batch_before_new_work(self):
        with patch.object(adapter.engine, "_realize_ready_decisions") as realize:
            callback = adapter._adapter_bindings()["_realize_ready_decisions"]
            with patch.object(adapter, "verified_realized_batch_count", side_effect=ValueError("old receipt invalid")):
                with self.assertRaisesRegex(ValueError, "old receipt invalid"):
                    callback("sessions")
            realize.assert_not_called()

    def test_execute_restores_every_binding_on_stage_failure(self):
        original = {name: getattr(adapter.engine, name) for name in adapter._adapter_bindings()}
        stages = []
        with patch.object(adapter.engine, "single_instance_lock", return_value=nullcontext()), \
                patch.object(adapter.engine, "_protected_hashes", return_value={}), \
                patch.object(adapter, "_verify_activation", side_effect=lambda **kw: stages.append(kw["static_only"])), \
                patch.object(adapter.previous, "_refresh_calendar", side_effect=lambda: stages.append("refresh")), \
                patch.object(adapter.engine, "execute", side_effect=RuntimeError("stage failure")):
            with self.assertRaisesRegex(RuntimeError, "stage failure"):
                adapter.execute()
        self.assertEqual(stages, [True, "refresh", False])
        for name, value in original.items():
            self.assertIs(getattr(adapter.engine, name), value, name)

    def test_inventory_records_new_actual_code_paths(self):
        base = {"_daily_artifact_inventory": lambda _: {}}
        with patch.object(adapter.previous, "_adapter_bindings", return_value=base):
            callback = adapter._adapter_bindings()["_daily_artifact_inventory"]
        result = callback({})
        for key, path in (("daily_script", Path(adapter.__file__).resolve()),
                          ("daily_engine", adapter.ROOT / "backtest/ndx_dynamic_shadow_daily_v3.py")):
            self.assertEqual(result[key], {"path": path.as_posix(), "sha256": adapter.file_sha256(path)})

    def test_noncanonical_final_rejected_before_receipt_read(self):
        with patch.object(adapter.acceptance, "verify_acceptance") as verifier:
            with self.assertRaisesRegex(adapter.NdxDynamicShadowDailyError, "not canonical"):
                adapter.verify_accepted_final(adapter.ROOT / "elsewhere/2026-10-01/manifest.json")
            verifier.assert_not_called()

    def test_empty_cumulative_inventory_uses_real_checker(self):
        with TemporaryDirectory() as directory, patch.object(adapter, "ROOT", Path(directory)):
            self.assertEqual(adapter.verified_realized_batch_count(), 0)


if __name__ == "__main__":
    unittest.main()
