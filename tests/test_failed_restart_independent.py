"""Read-only recovery admission attacks; never register or dispatch."""
import json
from pathlib import Path
from unittest.mock import patch
import unittest
import test_failed_paper_restart_preflight as fixtures


class IndependentRestart(unittest.TestCase):
    setUp = fixtures.FailedPaperRestartTests.setUp
    run_check = fixtures.FailedPaperRestartTests.run_check

    def test_dangling_database_and_sidecar_links_rejected(self):
        self.validated["request"]["identity"] = {
            "database_path": str(self.root / "account.sqlite3")}
        original = Path.is_symlink
        for suffix in ("", "-wal", "-shm", "-journal"):
            link = self.root / ("account.sqlite3" + suffix)
            with self.subTest(suffix=suffix), patch.object(
                    Path, "is_symlink",
                    lambda path: path == link or original(path)):
                with self.assertRaises(ValueError):
                    self.run_check()

    def test_all_success_receipts_block_without_database(self):
        for name in ("complete.json", "result.json", "start.json", "start_complete.json"):
            path = self.directory / "nested" / name
            path.parent.mkdir(exist_ok=True)
            path.write_text("{}")
            try:
                with self.assertRaisesRegex(ValueError, "SUCCESS_RECEIPT"):
                    self.run_check()
            finally:
                path.unlink()

    def test_shared_lock_and_existing_output_block(self):
        from scripts import register_quantity_v2_paper_protocol as registrar
        lock = self.root / registrar.LOCK
        lock.parent.mkdir(parents=True)
        lock.write_text("existing-owner")
        with self.assertRaisesRegex(ValueError, "LOCK"):
            self.run_check()
        self.assertEqual(lock.read_text(), "existing-owner")
        lock.unlink()
        (self.root / "new").mkdir()
        with self.assertRaisesRegex(ValueError, "NEW_REGISTRATION"):
            self.run_check()

    def test_success_is_only_preparation_and_changes_no_bytes(self):
        before = {str(p.relative_to(self.root)): p.read_bytes()
                  for p in self.root.rglob("*") if p.is_file()}
        result = self.run_check()
        after = {str(p.relative_to(self.root)): p.read_bytes()
                 for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(before, after)
        self.assertEqual(result["status"], "NEW_REGISTRATION_PREPARATION_ONLY")
        self.assertFalse(result["dispatch_authorized"])
        self.assertFalse(result["account_writes"])
        self.assertFalse(result["task_changes"])


if __name__ == "__main__":
    unittest.main()
