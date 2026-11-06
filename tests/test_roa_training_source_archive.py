import json
from hashlib import sha256
from pathlib import Path
import tempfile
import unittest
from scripts.research.archive_roa_training_sources import archive, check_or_restore, safe


class ArchiveTests(unittest.TestCase):
    def fixture(self,root):
        (root/"tmp").mkdir();(root/"tmp/a.bin").write_bytes(b"research")
        doc={"schema":"EXACT_RESEARCH_SOURCE_LIST_V1","source_hashes":{"tmp/a.bin":sha256(b"research").hexdigest()}}
        raw=json.dumps(doc).encode();(root/"tmp/list.json").write_bytes(raw)
        result=archive(root=root,source_list="tmp/list.json",source_list_sha256=sha256(raw).hexdigest(),destination="data/strategy_archives/test")
        return dict(root=root,directory=root/"data/strategy_archives/test",publication_sha256=result["publication_sha256"])

    def test_missing_restore_and_refuse_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);args=self.fixture(root)
            (root/"tmp/a.bin").unlink()
            self.assertEqual(check_or_restore(**args)["missing"],["tmp/a.bin"])
            self.assertFalse((root/"tmp/a.bin").exists())
            self.assertEqual(check_or_restore(**args,restore=True)["restored"],1)
            (root/"tmp/a.bin").write_bytes(b"new legitimate source")
            with self.assertRaisesRegex(ValueError,"REFUSE_OVERWRITE"):check_or_restore(**args,restore=True)
            self.assertEqual((root/"tmp/a.bin").read_bytes(),b"new legitimate source")

    def test_partial_corrupt_and_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);args=self.fixture(root)
            for name in ("../outside", "data/strategy_account/real.sqlite3", "tmp/credentials/key.json"):
                with self.assertRaises(ValueError):safe(root,name)
            (root/"tmp/a.bin").unlink()
            archived=args["directory"]/"inputs/tmp/a.bin"
            archived.write_bytes(b"corrupt")
            with self.assertRaises(ValueError):check_or_restore(**args,restore=True)
            self.assertFalse((root/"tmp/a.bin").exists())
            archived.unlink()
            with self.assertRaises((ValueError,FileNotFoundError)):check_or_restore(**args,restore=True)
            self.assertFalse((root/"tmp/a.bin").exists())


if __name__=="__main__":unittest.main()
