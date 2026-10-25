from pathlib import Path
from hashlib import sha256
import json
import unittest
from unittest.mock import patch
from data.strategy_daily_rebinding_reader import ArchivedRebindingDailyEvidenceReader
import test_strategy_daily_rebinding_reader as fixtures


class ArchivedReaderTests(unittest.TestCase):
    def fixture(self):
        helper=fixtures.ReaderTests();case,old,parent=helper.fixture()
        self.addCleanup(helper.doCleanups)
        archive=Path(case.temp.name)/"archive"
        reader=ArchivedRebindingDailyEvidenceReader(root=old.reader.root,archive_root=archive,
            parent_receipt_path=old.producer.parent_path,trusted_parent_sha256=old.producer.parent_sha,
            source_paths=old.producer.source_paths,release_path=old.release_path,
            trusted_release_sha256=old.release_sha,calendar_path=old.calendar_path)
        return case,reader,archive

    def test_ready_archives_exact_receipt_closure_and_embeds_signal_reference(self):
        c,r,a=self.fixture();before=(c.accounts.path.read_bytes(),c.targets.path.read_bytes())
        result=r(c.accounts.read(),c.targets.current(),c.clock)
        ref=result["evidence_archive"];raw=Path(ref["receipt_path"]).read_bytes()
        self.assertEqual(sha256(raw).hexdigest(),result["signal"]["evidence_id"])
        self.assertEqual(result["signal"]["evidence_archive"],ref)
        for name,digest in json.loads(raw)["source_sha256"].items():
            data=(Path(ref["receipt_path"]).parent/"sources"/(digest+".bin")).read_bytes()
            self.assertEqual(sha256(data).hexdigest(),digest)
        self.assertEqual(r(c.accounts.read(),c.targets.current(),c.clock),result)
        self.assertEqual(before,(c.accounts.path.read_bytes(),c.targets.path.read_bytes()))

    def test_wait_never_archives(self):
        c,r,a=self.fixture();r.release_sha=None
        self.assertEqual(r(c.accounts.read(),c.targets.current(),c.clock)["status"],"WAIT_POLICY_RELEASE")
        self.assertFalse(a.exists())

    def test_archive_failure_cannot_return_signal(self):
        c,r,a=self.fixture()
        with patch("data.strategy_daily_rebinding_reader.archive_rebound_evidence",
                   side_effect=OSError("archive unavailable")):
            with self.assertRaisesRegex(OSError,"archive unavailable"):
                r(c.accounts.read(),c.targets.current(),c.clock)
        self.assertFalse(a.exists())

    def test_reused_complete_source_corruption_fails(self):
        c,r,a=self.fixture();result=r(c.accounts.read(),c.targets.current(),c.clock)
        path=next(a.rglob("*.bin"));path.write_bytes(b"corrupt")
        with self.assertRaisesRegex(ValueError,"BYTES_CHANGED"):
            r(c.accounts.read(),c.targets.current(),c.clock)
