from __future__ import annotations

from contextlib import nullcontext, redirect_stderr
import io
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from scripts import ndx_dynamic_shadow_daily_v3 as daily


class ReviewedDailyV3Tests(unittest.TestCase):
    def test_scoped_bindings_restore_after_exception(self):
        original = daily.engine.CALENDAR_MANIFEST
        with self.assertRaisesRegex(RuntimeError, "fixture"):
            with daily.scoped_engine_bindings({"CALENDAR_MANIFEST": Path("fixture")}):
                self.assertEqual(daily.engine.CALENDAR_MANIFEST, Path("fixture"))
                raise RuntimeError("fixture")
        self.assertEqual(daily.engine.CALENDAR_MANIFEST, original)

    def test_activation_precedes_any_calendar_refresh(self):
        events = []
        with (
            patch.object(daily.engine, "single_instance_lock", return_value=nullcontext()),
            patch.object(daily.engine, "_protected_hashes", return_value={"state": "fixed"}),
            patch.object(daily, "_verify_activation", side_effect=lambda **kw: events.append(kw["static_only"])),
            patch.object(daily, "_refresh_calendar", side_effect=lambda: events.append("refresh")),
            patch.object(daily, "_adapter_bindings", return_value={}),
            patch.object(daily.engine, "execute", return_value={"status": "fixture"}),
        ):
            self.assertEqual(daily.execute(), {"status": "fixture"})
        self.assertEqual(events, [True, "refresh", False])

    def test_missing_activation_cannot_refresh_or_run(self):
        with (
            patch.object(daily.engine, "single_instance_lock", return_value=nullcontext()),
            patch.object(daily.engine, "_protected_hashes", return_value={}),
            patch.object(daily, "_verify_activation", side_effect=ValueError("missing activation")),
            patch.object(daily, "_refresh_calendar") as refresh,
            patch.object(daily.engine, "execute") as execute,
        ):
            with self.assertRaises(ValueError):
                daily.execute()
        refresh.assert_not_called()
        execute.assert_not_called()

    def test_protected_hashes_are_checked_on_stage_failure(self):
        with (
            patch.object(daily.engine, "single_instance_lock", return_value=nullcontext()),
            patch.object(daily.engine, "_protected_hashes", side_effect=[{"state": "a"}, {"state": "b"}]),
            patch.object(daily, "_verify_activation", side_effect=ValueError("fixture")),
        ):
            with self.assertRaisesRegex(daily.NdxDynamicShadowDailyError, "protected live files changed"):
                daily.execute()

    def test_cli_preserves_retry_and_terminal_exit_codes(self):
        for code in (2, 4, 75):
            with self.subTest(code=code), redirect_stderr(io.StringIO()), patch.object(
                daily, "execute", side_effect=daily.ResearchStageFailure("fixture", code),
            ):
                self.assertEqual(daily.main(["--execute"]), code)

    def test_outer_deadline_uses_no_backfill_exception_contract(self):
        with patch.object(daily, "run_process_tree", side_effect=subprocess.TimeoutExpired("fixture", 1)):
            with self.assertRaisesRegex(daily.NdxDynamicShadowDailyError, "exceeded the pre-open"):
                daily._run_checked(["fixture"], timeout_seconds=1)

    def test_daily_does_not_implicitly_initialize_calendar(self):
        with patch.object(daily, "CALENDAR", Path("missing-calendar-fixture.json")), patch.object(
            daily.engine, "get_bars",
        ) as refresh:
            with self.assertRaisesRegex(daily.NdxDynamicShadowDailyError, "initialized explicitly"):
                daily._refresh_calendar()
        refresh.assert_not_called()


if __name__ == "__main__":
    unittest.main()
