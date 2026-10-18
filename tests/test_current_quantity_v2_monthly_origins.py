"""Accepted raw origins from frozen genesis and reopened temporary monthly blobs."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
import test_current_quantity_v2_current_cash_plan as cash
from test_current_quantity_v2_current_cash_continuation import fixture as cash_chain
from test_current_quantity_v2_monthly_sources import fixture as monthly_fixture
from data.current_quantity_v2_monthly_origins import MonthlyOriginReader
from data.current_quantity_v2_monthly_service import QuantityV2MonthlySourceBridge


class OriginsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cash.CurrentCashTests.setUpClass()
    @classmethod
    def tearDownClass(cls):cash.CurrentCashTests.tearDownClass()

    def test_current_cash_frozen_origins_positive_held_only(self):
        state,_,_=cash_chain(cash.CurrentCashTests.args);before=deepcopy(state)
        result=MonthlyOriginReader()({'state':state})
        original=state['ledger']['acceptance']['proposal']
        expected=next(r['source_hashes'] for r in original['rows'] if r['security_id']=='A')
        self.assertEqual(result['source_hashes'],expected)
        self.assertEqual(set(result['files']),set(expected));self.assertEqual(state,before)
        result['files'].clear();self.assertTrue(MonthlyOriginReader()({'state':state})['files'])
        with patch('data.current_quantity_v2_monthly_origins.MAX_SOURCE_BYTES',1):
            with self.assertRaisesRegex(ValueError,'SIZE_LIMIT'):MonthlyOriginReader()({'state':state})

    def monthly(self,folder):
        source,paper,state,did,clock,_,_=monthly_fixture(folder);source.capture(state)
        bridge=QuantityV2MonthlySourceBridge(store=paper.store,resolver=source.resolve,clock=lambda:clock[0])
        aid=state['ledger']['account_id'];p=bridge.preview(account_id=aid,decision_id=did,expected_revision=state['ledger']['revision'])
        state=paper.store.accept_monthly_retarget(account_id=aid,proposal_id=p['proposal_id'],operation_id='month',expected_revision=state['ledger']['revision'],
            factory=lambda current,now:bridge.monthly_resolver(current,p['proposal_id'],now),clock=lambda:clock[0])
        return state,source.storage_root/'blobs'

    def test_reopened_archive_uses_exact_hash_not_capture_manifest(self):
        with TemporaryDirectory() as folder:
            state,root=self.monthly(folder)
            result=MonthlyOriginReader(monthly_blob_root=root)({'state':state})
            expected=state['ledger']['active_monthly_acceptance']['proposal']['causal_inputs']['execution_references']['A']['source_hashes']
            self.assertEqual(result['source_hashes'],expected)
            self.assertEqual(MonthlyOriginReader(monthly_blob_root=root)({'state':state}),result)
            path=root/next(iter(expected.values()));path.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'BYTES_CHANGED'):MonthlyOriginReader(monthly_blob_root=root)({'state':state})

    def test_missing_and_symlink_fail_closed_without_writes(self):
        with TemporaryDirectory() as folder:
            state,root=self.monthly(folder)
            with self.assertRaisesRegex(ValueError,'ARCHIVE_REQUIRED'):MonthlyOriginReader()({'state':state})
            expected=state['ledger']['active_monthly_acceptance']['proposal']['causal_inputs']['execution_references']['A']['source_hashes']
            path=root/next(iter(expected.values()));raw=path.read_bytes();path.unlink()
            with self.assertRaisesRegex(ValueError,'BYTES_MISSING'):MonthlyOriginReader(monthly_blob_root=root)({'state':state})
            outside=Path(folder)/'outside';outside.write_bytes(raw)
            path.symlink_to(outside)
            with self.assertRaisesRegex(ValueError,'PATH_ESCAPE'):MonthlyOriginReader(monthly_blob_root=root)({'state':state})
            self.assertEqual(outside.read_bytes(),raw)

if __name__=='__main__':unittest.main()
