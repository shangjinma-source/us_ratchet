"""Offline regression on frozen RKLB evidence; no admission/descriptor rewrite."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import json
import unittest

from data.current_quantity_v2_current_cash_sources import CurrentQuantityV2CurrentCashSources


class RklbIdentityPathTests(unittest.TestCase):
    def fixture(self):
        root=Path(__file__).resolve().parents[1]
        receipt=json.loads((root/'tmp/tri98_runtime_execution_admission_20261016_v2/receipt.json').read_bytes())
        descriptor=json.loads((root/receipt['descriptor_path']).read_bytes())
        pins=descriptor['source_hashes'];files={p:(root/p).read_bytes() for p in pins}
        self.assertTrue(all(sha256(files[p]).hexdigest()==h for p,h in pins.items()))
        arguments=json.loads(files[descriptor['input_path']])['search_arguments']
        # Identity-only projection, never passed to an execution/acceptance API.
        decision=dict(decision_date=arguments['decision_date'],binding=dict(search_arguments=dict(metadata=arguments['metadata'])))
        source=CurrentQuantityV2CurrentCashSources(root=root,snapshot_service=None,server_account_id='offline-test',
            identity_manifest_path=receipt['identity_manifest_path'])
        return source,decision,files,pins

    def test_original_frozen_rklb_windows_source_key_passes_unchanged(self):
        source,decision,files,pins=self.fixture();before=deepcopy(files)
        result=source._identity(decision,files,pins,'security:0001819994:773121108','2026-10-16')
        self.assertEqual(result['ticker'],'RKLB');self.assertEqual(result['security_class'],'Common stock')
        self.assertEqual(result['issuer_id'],'issuer:0001819994');self.assertEqual(files,before)

    def test_conflicting_alias_escape_and_hash_mismatch_still_rejected(self):
        path='tmp/next12_identity_admission_20261014_v1/identity_admission.json'
        notice='tmp/next12_identity_primary_capture_20261014_v1/rklb_notice.response.bin'
        for mode,reason in [('conflict','CLASS_SOURCE_HASH_ALIAS_CONFLICT'),('escape','SAFE_SOURCE_PATH_REQUIRED'),
                            ('mismatch','CLASS_ADMISSION_SOURCE_MISMATCH')]:
            with self.subTest(mode=mode):
                source,decision,files,pins=self.fixture();doc=json.loads(files[path])
                if mode=='conflict':doc['source_hashes'][notice]='0'*64
                if mode=='escape':doc['source_hashes']['..\\escape.json']='0'*64
                if mode=='mismatch':doc['source_hashes'][notice.replace('/','\\')]='0'*64
                files[path]=json.dumps(doc).encode()
                with self.assertRaisesRegex(ValueError,reason):
                    source._identity(decision,files,pins,'security:0001819994:773121108','2026-10-16')


if __name__=='__main__':unittest.main()
