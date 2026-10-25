from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from core.strategy_account_ledger import canonical
from data.strategy_daily_rebound_archive import archive_rebound_evidence


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "archive"
        self.files = {"../../logical-only": b"source", "duplicate": b"source"}
        self.receipt = canonical(dict(schema="SERVER_REVIEWED_DAILY_EVIDENCE_V1",
            release_sha256=None,
            source_sha256={k: sha256(v).hexdigest() for k, v in self.files.items()}))

    def save(self):
        return archive_rebound_evidence(root=self.root, receipt_bytes=self.receipt, files=self.files)

    def test_exact_bytes_and_idempotent_reuse_without_approval(self):
        saved = self.save()
        self.assertEqual(saved, self.save())
        self.assertEqual(Path(saved["receipt_path"]).read_bytes(), self.receipt)
        self.assertEqual(len(list(self.root.rglob("*.bin"))), 1)
        self.assertFalse(saved["policy_approval_created"])
        self.assertFalse((Path(self.temp.name) / "logical-only").exists())

    def test_partial_archive_preserved_and_not_retried(self):
        folder = self.root / sha256(self.receipt).hexdigest()
        folder.mkdir(parents=True)
        (folder / "receipt.json").write_bytes(b"partial")
        with self.assertRaisesRegex(ValueError, "RECOVERY_REQUIRED"):
            self.save()
        self.assertEqual((folder / "receipt.json").read_bytes(), b"partial")

    def test_completed_archive_tampering_refused(self):
        saved = self.save()
        Path(saved["receipt_path"]).write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "BYTES_CHANGED"):
            self.save()

    def test_source_hash_mismatch_creates_nothing(self):
        self.files["duplicate"] = b"tampered"
        with self.assertRaisesRegex(ValueError, "SOURCE_CHANGED"):
            self.save()
        self.assertFalse(self.root.exists())


if __name__ == "__main__":
    unittest.main()
