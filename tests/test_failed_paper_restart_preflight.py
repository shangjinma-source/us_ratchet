import json
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.preflight_failed_paper_restart import inspect_failed_state, run


class FailedPaperRestartTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.directory = self.root / "old/runtime"
        for name in ("bootstrap_reconciliation_required.json",
                     "execution_reconciliation_required.json",
                     "bootstrap-attempt/failed.json", "bootstrap-attempt/started.json"):
            path = self.directory / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"request_sha256": "abc"}))
        self.descriptor = dict(registration_directory="old", request_sha256="abc", log_directory="logs")
        self.validated = dict(database_path=str(self.root / "account.sqlite3"),
                             request={"evaluation": {"start_session": "2026-10-19"},
                                      "identity": {"database_path": str(self.root / "account.sqlite3")}},
                             calendar={"sessions": [{"date": "2026-10-20",
                                                     "open_at": "2026-10-20T13:30:00+00:00",
                                                     "close_at": "2026-10-20T20:00:00+00:00"}]})
        self.now = datetime(2026, 10, 20, 8, tzinfo=timezone.utc)

    def run_check(self, target="new", session="2026-10-20"):
        return inspect_failed_state(self.root, self.descriptor, self.validated, target, session, self.now)

    def test_read_only_success(self):
        before = sorted(str(p) for p in self.root.rglob("*"))
        self.assertFalse(self.run_check()["dispatch_authorized"])
        self.assertEqual(before, sorted(str(p) for p in self.root.rglob("*")))

    def test_database_and_sidecars_block(self):
        for suffix in ("", "-wal", "-shm", "-journal"):
            with self.subTest(suffix=suffix):
                path = self.root / ("account.sqlite3" + suffix)
                path.touch()
                with self.assertRaisesRegex(ValueError, "DATABASE_OR_SIDECAR"):
                    self.run_check()
                path.unlink()

    def test_success_receipt_blocks(self):
        (self.directory / "start_complete.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "SUCCESS_RECEIPT"):
            self.run_check()

    def test_paths_time_and_hash_binding(self):
        for target in ("../escape", "old/new", "old"):
            with self.subTest(target=target), self.assertRaises(ValueError):
                self.run_check(target=target)
        with self.assertRaisesRegex(ValueError, "ADVANCE"):
            self.run_check(session="2026-10-19")
        self.now = datetime(2026, 10, 20, 14, tzinfo=timezone.utc)
        with self.assertRaisesRegex(ValueError, "ALREADY_PASSED"):
            self.run_check()
        self.now = datetime(2026, 10, 20, 8, tzinfo=timezone.utc)
        (self.directory / "bootstrap-attempt/failed.json").write_text('{"request_sha256":"changed"}')
        with self.assertRaisesRegex(ValueError, "FAILURE_REQUEST"):
            self.run_check()

    def test_descriptor_link_checked_before_resolve_and_read(self):
        with patch.object(Path, "is_symlink", return_value=True), \
                patch.object(Path, "resolve") as resolve, \
                patch.object(Path, "read_bytes") as read:
            with self.assertRaisesRegex(ValueError, "DESCRIPTOR_LINK"):
                run(descriptor_path=str(self.root / "link.json"),
                    expected_descriptor_sha256="unused", new_directory="new",
                    start_session="2026-10-20")
            resolve.assert_not_called()
            read.assert_not_called()
