"""Immutable capture blob reuse keeps bounded integrity and create-only races."""
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import os
import unittest
from unittest.mock import patch
from data.current_quantity_v2_monthly_capture_audit import publish_blob


class CaptureBlobTests(unittest.TestCase):
    def test_matching_existing_bytes_skip_fsync_but_missing_is_durable(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);raw=b'captured bytes'
            with patch('os.fsync',wraps=os.fsync) as sync:
                digest=publish_blob(root,raw,100)
                self.assertEqual(sync.call_count,1)
                self.assertEqual(publish_blob(root,raw,100),digest)
                self.assertEqual(sync.call_count,1)

    def test_corrupt_and_oversized_existing_bytes_refused(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);raw=b'good';path=root/'blobs'/sha256(raw).hexdigest()
            path.parent.mkdir();path.write_bytes(b'evil')
            with self.assertRaisesRegex(ValueError,'CONFLICT'):publish_blob(root,raw,10)
            path.write_bytes(b'x'*11)
            with self.assertRaisesRegex(ValueError,'SIZE_LIMIT'):publish_blob(root,raw,10)

    def test_symlink_refused_even_with_matching_target(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);raw=b'good';path=root/'blobs'/sha256(raw).hexdigest()
            path.parent.mkdir();target=root/'other';target.write_bytes(raw)
            try:path.symlink_to(target)
            except OSError as error:self.skipTest('Host disallows test symlink: '+type(error).__name__)
            with self.assertRaisesRegex(ValueError,'PATH_ESCAPE|SYMLINK'):publish_blob(root,raw,10)

    def test_concurrent_creation_keeps_exact_byte_conflict_check(self):
        for competitor in (b'good',b'evil'):
            with self.subTest(competitor=competitor),TemporaryDirectory() as folder:
                root=Path(folder);raw=b'good';path=root/'blobs'/sha256(raw).hexdigest()
                def concurrent_link(source,destination):
                    Path(destination).write_bytes(competitor)
                    raise FileExistsError()
                with patch('os.link',side_effect=concurrent_link):
                    if competitor==raw:publish_blob(root,raw,10)
                    else:
                        with self.assertRaisesRegex(ValueError,'CONFLICT'):publish_blob(root,raw,10)
                self.assertEqual(path.read_bytes(),competitor)
                self.assertEqual(list(path.parent.glob('.pending-*')),[])

if __name__=='__main__':unittest.main()
