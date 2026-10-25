import json
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from core.strategy_account_ledger import canonical
from data.paper_source_archive_reader_v1 import read_archive


class ArchiveReaderTests(TestCase):
    def fixture(self, root):
        root=Path(root);(root/'blobs').mkdir()
        source=b'raw evidence';pin=sha256(source).hexdigest()
        parent=canonical({'source_sha256':{'daily.bin':pin}});key=sha256(parent).hexdigest()
        payload={'parent-receipt.json':parent,'configuration.json':canonical({'security_id':'A','release_sha256':None}),
                 'source-root/daily.bin':source}
        folder=root/key;folder.mkdir()
        manifest={'status':'UNREGISTERED_SOURCE_ARCHIVE','parent_sha256':key,'security_id':'A','registration_created':False,
                  'files':{n:sha256(b).hexdigest() for n,b in payload.items()}}
        for name,body in payload.items():(root/'blobs'/(sha256(body).hexdigest()+'.bin')).write_bytes(body)
        self.seal(folder,manifest)
        return key,folder,manifest,pin

    def seal(self, folder, manifest):
        raw=canonical(manifest);(folder/'manifest.json').write_bytes(raw)
        (folder/'complete.json').write_bytes(canonical({'manifest_sha256':sha256(raw).hexdigest(),'readback_verified':True}))

    def test_reader_uses_only_archive(self):
        with TemporaryDirectory() as root:
            key,_,_,_=self.fixture(root)
            result=read_archive(root,key)
            self.assertEqual(result['files'],{'daily.bin':b'raw evidence'})
            self.assertFalse(result['source_admission_performed'])

    def test_corrupt_blob_and_missing_completion_rejected(self):
        with TemporaryDirectory() as root:
            key,folder,_,pin=self.fixture(root)
            (Path(root)/'blobs'/(pin+'.bin')).write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'BLOB_CHANGED'):read_archive(root,key)
            (folder/'complete.json').unlink()
            with self.assertRaises(FileNotFoundError):read_archive(root,key)

    def test_resealed_manifest_cannot_escape_or_omit_parent_sources(self):
        with TemporaryDirectory() as root:
            key,folder,manifest,pin=self.fixture(root)
            manifest['files']['../outside']=pin;self.seal(folder,manifest)
            with self.assertRaisesRegex(ValueError,'LOGICAL_PATH'):read_archive(root,key)
            del manifest['files']['../outside'];del manifest['files']['source-root/daily.bin'];self.seal(folder,manifest)
            with self.assertRaisesRegex(ValueError,'SOURCE_DOMAIN'):read_archive(root,key)
