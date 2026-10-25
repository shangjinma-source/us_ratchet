"""Independent negative-path checks; isolated real SQLite fixtures only."""
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
import test_registered_paper_settlement_runtime as fixtures
from backtest.registered_paper_settlement_runtime import finalize_registered_paper


class SettlementIndependentReview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.FinalSettlementTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        fixtures.FinalSettlementTests.tearDownClass()

    def test_failed_and_prepared_operations_block_without_recovery(self):
        for status in ('FAILED', 'PREPARED'):
            with self.subTest(status=status), TemporaryDirectory() as folder:
                args,captures,_,_=fixtures.FinalSettlementTests().setup_final(folder)
                store=args['store']
                request=dict(simulation_id=args['simulation_id'],expected_revision=args['expected_revision'],
                    operation_id='independent-interrupted',request={'kind':'synthetic-interrupted'})
                def fail(_): raise RuntimeError('synthetic failed transform')
                if status=='FAILED':
                    with self.assertRaises(RuntimeError):store.apply(**request,transform=fail)
                else:
                    with patch.object(store,'_commit',side_effect=RuntimeError('synthetic lost commit')):
                        with self.assertRaises(RuntimeError):store.apply(**request,transform=lambda value:value)
                self.assertEqual(store.inspect_operations(args['simulation_id'])['operations'][0]['status'],status)
                before=store.path.read_bytes()
                with patch.object(store,'recover',side_effect=AssertionError('must not recover')):
                    with self.assertRaisesRegex(ValueError,'SETTLEMENT_RECOVERY_REQUIRED_NO_AUTOMATIC_RETRY'):
                        finalize_registered_paper(**args)
                self.assertEqual(before,store.path.read_bytes())
                self.assertEqual(captures,[])

    def test_close_provider_exception_keeps_completed_settlement_and_explicit_retry(self):
        with TemporaryDirectory() as folder:
            args,captures,_,_=fixtures.FinalSettlementTests().setup_final(folder)
            original=args['close_arguments']
            def fail(*_):raise RuntimeError('close transport failed')
            args['close_arguments']=fail
            with self.assertRaisesRegex(RuntimeError,'close transport failed'):finalize_registered_paper(**args)
            current=args['store'].read(args['simulation_id'])
            self.assertTrue(all(o['closed']=='FILLED' for o in current['simulation']['chain']['ledger']['orders'].values()))
            self.assertEqual(current['simulation']['valuation']['records'],[])
            before=len(captures)
            args.update(expected_revision=current['revision'],close_arguments=original)
            result=finalize_registered_paper(**args)
            self.assertEqual(result['settlement_status'],'FINALIZED_DECLARED_END')
            self.assertEqual(len(captures),before)

if __name__=='__main__':unittest.main()
