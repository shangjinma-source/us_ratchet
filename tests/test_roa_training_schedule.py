import tempfile
import unittest
from pathlib import Path
from hashlib import sha256
from scripts.research.build_roa_training_schedule import schedule_dates, checked_read, write_immutable


class TrainingScheduleTests(unittest.TestCase):
    def test_december_boundary_and_early_close(self):
        dates, intersection = schedule_dates("2026-11-30", "2026-12-31", {"2026-12-25"},
                                            ["2026-11-30", "2026-12-01"])
        self.assertEqual(dates[:2], ["2026-11-30", "2026-12-01"])
        self.assertIn("2026-12-24", dates)
        self.assertNotIn("2026-12-25", dates)
        self.assertEqual(dates[-1], "2026-12-31")
        self.assertEqual(intersection["count"], 2)

    def test_carter_closure(self):
        dates, _ = schedule_dates("2025-01-08", "2025-01-10", {"2025-01-09"},
                                  ["2025-01-08", "2025-01-10"])
        self.assertEqual(dates, ["2025-01-08", "2025-01-10"])

    def test_year_scope_and_intersection(self):
        with self.assertRaisesRegex(ValueError, "YEAR_COVERAGE"):
            schedule_dates("2026-12-30", "2027-01-04", set(), ["2026-12-30"])
        for runtime in (["2026-12-23", "2026-12-28"],
                        ["2026-12-23", "2026-12-24", "2026-12-25", "2026-12-28"]):
            with self.assertRaisesRegex(ValueError, "INTERSECTION_MISMATCH"):
                schedule_dates("2026-12-23", "2026-12-28", {"2026-12-25"}, runtime)
        with self.assertRaisesRegex(ValueError, "DATES_INVALID"):
            schedule_dates("2026-12-23", "2026-12-28", set(), ["2026-12-23"] * 2)

    def test_hash_and_immutable_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "source").write_bytes(b"official")
            pins = {}
            checked_read(root, "source", sha256(b"official").hexdigest(), pins)
            (root / "source").write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "HASH_CHANGED"):
                checked_read(root, "source", pins["source"], {})
            target = root / "schedule.json"
            first = write_immutable(target, {"dates": []})
            self.assertEqual(first, write_immutable(target, {"dates": []}))
            with self.assertRaisesRegex(ValueError, "ALREADY_EXISTS"):
                write_immutable(target, {"dates": ["2026-12-01"]})


if __name__ == "__main__":
    unittest.main()
