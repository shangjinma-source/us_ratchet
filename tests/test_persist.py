from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from core.persist import (
    advice_snapshot_log,
    advice_snapshot_storage,
    iter_advice_snapshots,
    load_advice_snapshots,
    rebuild_advice_snapshot_meta,
    scan_advice_snapshot_journal,
)


class AdviceSnapshotPersistenceTests(unittest.TestCase):
    def test_append_is_readable_after_a_new_loader_and_tracks_sidecar(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "advice_snapshots.jsonl"
            advice_snapshot_log({"snapshot_id": "one", "value": 1}, path=path)
            advice_snapshot_log({"snapshot_id": "two", "value": 2}, path=path)

            # The loader is intentionally called after the writer returns,
            # matching a process restart boundary rather than an in-memory list.
            rows = load_advice_snapshots(limit=10, path=path)
            self.assertEqual([row["snapshot_id"] for row in rows], ["one", "two"])

            storage = advice_snapshot_storage(path)
            self.assertTrue(storage["persistent"])
            self.assertEqual(storage["last_snapshot_id"], "two")
            self.assertEqual(storage["row_count"], 2)
            self.assertEqual(storage["valid_row_count"], 2)
            self.assertEqual(storage["invalid_row_count"], 0)
            self.assertEqual(storage["durability"], "append_flush_fsync")
            meta_path = Path(storage["metadata_path"])
            self.assertTrue(meta_path.exists())
            self.assertEqual(json.loads(meta_path.read_text(encoding="utf-8"))["row_count"], 2)

    def test_tail_reader_returns_only_latest_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "advice_snapshots.jsonl"
            for index in range(5):
                advice_snapshot_log({"snapshot_id": str(index)}, path=path)
            rows = load_advice_snapshots(limit=2, path=path)
            self.assertEqual([row["snapshot_id"] for row in rows], ["3", "4"])

    def test_full_history_iterator_survives_tail_reader_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "advice_snapshots.jsonl"
            for index in range(5):
                advice_snapshot_log({"snapshot_id": str(index)}, path=path)
            rows = list(iter_advice_snapshots(path))
            self.assertEqual([row["snapshot_id"] for row in rows], ["0", "1", "2", "3", "4"])

    def test_rebuild_meta_recovers_existing_journal_range(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "advice_snapshots.jsonl"
            advice_snapshot_log({"snapshot_id": "one"}, path=path)
            meta_path = path.with_suffix(".meta.json")
            meta_path.write_text(
                json.dumps({"row_count": None, "first_ts": "wrong"}),
                encoding="utf-8",
            )
            repaired = rebuild_advice_snapshot_meta(path)
            self.assertEqual(repaired["row_count"], 1)
            self.assertEqual(repaired["valid_row_count"], 1)
            self.assertNotEqual(repaired["first_ts"], "wrong")
            advice_snapshot_log({"snapshot_id": "two"}, path=path)
            persisted = json.loads(meta_path.read_text(encoding="utf-8"))
            self.assertEqual(persisted["row_count"], 2)
            self.assertEqual(persisted["valid_row_count"], 2)
            self.assertEqual(persisted["invalid_row_count"], 0)

    def test_read_only_full_scan_does_not_repair_stale_sidecar(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "advice_snapshots.jsonl"
            advice_snapshot_log({"snapshot_id": "one"}, path=path)
            meta_path = path.with_suffix(".meta.json")
            stale = json.loads(meta_path.read_text(encoding="utf-8"))
            stale["row_count"] = 99
            meta_path.write_text(json.dumps(stale), encoding="utf-8")

            scanned = scan_advice_snapshot_journal(path)

            self.assertEqual(scanned["row_count"], 1)
            self.assertEqual(
                json.loads(meta_path.read_text(encoding="utf-8"))["row_count"], 99
            )


if __name__ == "__main__":
    unittest.main()
