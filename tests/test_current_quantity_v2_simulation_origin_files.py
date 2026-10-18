from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from data.current_quantity_v2_simulation_origin_files import SimulationOriginFilesReader
from backtest.current_quantity_v2_simulated_settlement import _references


class OriginFilesTests(unittest.TestCase):
    def test_cash_actual_frozen_bytes_and_wrong_reference(self):
        import test_current_quantity_v2_current_cash_plan as base
        from test_current_quantity_v2_current_cash_ledger import frozen_fixture
        from data.current_quantity_v2_paper_ledger import accept_proposal
        from data.current_quantity_v2_paper_chain import create_chain
        base.CurrentCashTests.setUpClass()
        try:
            proposal,args=frozen_fixture(base.CurrentCashTests.args)
            state={'chain':create_chain(accept_proposal(proposal,account_state=args['account_state'],now=args['now']))}
            reader=SimulationOriginFilesReader()
            for ref in _references(state['chain']).values():
                self.assertEqual(reader(state,ref),{p:args['execution_package']['files'][p] for p in ref['source_hashes']})
                wrong=deepcopy(ref);wrong['captured_at']='2026-10-01T00:00:00+00:00'
                with self.assertRaisesRegex(ValueError,'ORIGIN_REFERENCE_NOT_CURRENT'):reader(state,wrong)
        finally:base.CurrentCashTests.tearDownClass()

    def test_explicit_blob_root_hash_not_original_filename(self):
        from test_current_quantity_v2_late_unit_review import real_pin_fixture,origins
        from test_current_quantity_v2_simulated_settlement import fixture
        from data.current_quantity_v2_monthly_capture_audit import publish_blob
        with TemporaryDirectory() as folder,patch('test_current_quantity_v2_paper_ledger.fixture',side_effect=real_pin_fixture):
            state,_,_=fixture();root=Path(folder)/'audit';reader=SimulationOriginFilesReader(capture_audit_roots=[root])
            self.assertFalse(root.exists())
            for ref in _references(state['chain']).values():
                with self.assertRaisesRegex(ValueError,'ORIGIN_SOURCE_MISSING'):reader(state,ref)
                files=origins(ref)
                for raw in files.values():publish_blob(root,raw,4*1024*1024)
                self.assertEqual(reader(state,ref),files)
            ref=next(iter(_references(state['chain']).values()));digest=next(iter(ref['source_hashes'].values()))
            target=root/'blobs'/digest;target.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'ORIGIN_SOURCE_CHANGED'):reader(state,ref)
            target.unlink()
            other=root/'other';other.write_bytes(b'not a valid blob')
            try:target.symlink_to(other)
            except OSError:self.skipTest('Host lacks symlink creation permission')
            with self.assertRaisesRegex(ValueError,'ORIGIN_SYMLINK_REFUSED'):reader(state,ref)


if __name__=='__main__':unittest.main()
