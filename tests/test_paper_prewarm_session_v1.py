import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timezone, timedelta
from hashlib import sha256
from scripts.paper_prewarm_session_v1 import run_prewarmed_session, verify_pin_groups
from scripts.paper_prewarm_session_v1 import RegisteredPaperPrewarmValidationV1


class PrewarmTests(unittest.TestCase):
    def exercise(self, *, import_delay=120, final_delay=0, mutate=False, armed=True):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        source = root / "source.py"
        source.write_text("fixed", encoding="utf8")
        pins = {"source.py": sha256(source.read_bytes()).hexdigest()}
        point = [datetime(2026, 10, 21, 13, 50, tzinfo=timezone.utc)]
        seconds = [0.]
        events, calls = [], []
        calendar = {"sessions": [{"date": "2026-10-21",
                    "open_at": "2026-10-21T13:30:00+00:00",
                    "close_at": "2026-10-21T20:00:00+00:00"}]}
        def advance(value):
            point[0] += timedelta(seconds=value)
            seconds[0] += value
        def validate():
            calls.append("validate")
            if calls.count("validate") == 2:
                advance(final_delay)
                if mutate:
                    source.write_text("changed", encoding="utf8")
            verify_pin_groups(root, [pins, pins])
            return {"calendar": calendar}
        def dispatch():
            calls.append("dispatch")
            self.assertEqual(point[0].hour, 14)
            self.assertEqual(point[0].minute, 0)
            return {"status": "FIXTURE_ONLY"}
        options = dict(calendar=calendar,
                       session="2026-10-21", lock_path=root / "prewarm.lock",
                       load_dependencies=lambda: advance(import_delay),
                       validate_current=validate, dispatch=dispatch,
                       emit=events.append, armed=armed,
                       clock=lambda: point[0], monotonic=lambda: seconds[0], sleep=advance)
        return options, calls, events, root, pins

    def test_cold_import_before_decision_and_fresh_final_validation(self):
        options, calls, events, root, pins = self.exercise()
        result = run_prewarmed_session(**options)
        self.assertEqual(result["dispatches"], 1)
        self.assertEqual(calls, ["validate", "validate", "dispatch"])
        self.assertEqual(events[0]["stage"], "ENTRY_BEFORE_IMPORT")
        self.assertEqual(events[1]["elapsed_seconds"], 120)
        self.assertEqual(verify_pin_groups(root, [pins, pins])["unique_files_read"], 1)

    def test_slow_import_and_final_gate_reject_without_dispatch(self):
        for kwargs in ({"import_delay": 661}, {"final_delay": 60}):
            options, calls, *_ = self.exercise(**kwargs)
            with self.assertRaisesRegex(ValueError, "MISSED_DECISION_WINDOW"):
                run_prewarmed_session(**options)
            self.assertNotIn("dispatch", calls)

    def test_source_change_rejected_and_check_only_never_waits(self):
        options, calls, *_ = self.exercise(mutate=True)
        with self.assertRaisesRegex(ValueError, "PIN_CHANGED"):
            run_prewarmed_session(**options)
        self.assertNotIn("dispatch", calls)
        options, calls, events, *_ = self.exercise(armed=False)
        self.assertEqual(run_prewarmed_session(**options)["status"], "PREWARM_CHECK_ONLY")
        self.assertEqual(calls, ["validate"])
        self.assertEqual(events[-1]["elapsed_seconds"], 120)

    def test_duplicate_lock_and_conflicting_pins(self):
        options, calls, events, root, pins = self.exercise()
        options["lock_path"].write_text("existing")
        self.assertEqual(run_prewarmed_session(**options)["dispatches"], 0)
        self.assertEqual(calls, [])
        self.assertEqual(options["lock_path"].read_text(), "existing")
        with self.assertRaisesRegex(ValueError, "PIN_CONFLICT"):
            verify_pin_groups(root, [pins, {"source.py": "0"*64}])

    def test_clock_rollback_and_wait_overshoot(self):
        options, calls, *_ = self.exercise()
        point = [datetime(2026, 10, 21, 13, 50, tzinfo=timezone.utc)]
        options["clock"] = lambda: point[0]
        options["load_dependencies"] = lambda: point.__setitem__(0, point[0]-timedelta(seconds=1))
        with self.assertRaisesRegex(ValueError, "CLOCK_ROLLBACK"):
            run_prewarmed_session(**options)
        self.assertNotIn("dispatch", calls)
        options, calls, *_ = self.exercise()
        original = options["sleep"]
        options["sleep"] = lambda _: original(1000)
        with self.assertRaisesRegex(ValueError, "MISSED_DECISION_WINDOW"):
            run_prewarmed_session(**options)
        self.assertNotIn("dispatch", calls)

    def test_real_registered_bundle_read_only_validation(self):
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        from test_run_registered_paper_automation import setup
        with tempfile.TemporaryDirectory() as folder:
            args, point, store = setup(folder)
            before = store.path.read_bytes()
            adapter = RegisteredPaperPrewarmValidationV1(
                args["descriptor_path"], args["expected_descriptor_sha256"],
                clock=lambda: point)
            adapter.load_dependencies()
            result = adapter.validate()
            self.assertFalse(result["account_writes"])
            self.assertEqual(result["strategy_dispatches"], 0)
            self.assertEqual(store.path.read_bytes(), before)
            (Path(folder) / "scripts/run_registered_paper_automation.py").write_text("drift")
            with self.assertRaisesRegex(ValueError, "PIN_CHANGED"):
                adapter.validate()
            self.assertEqual(store.path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
