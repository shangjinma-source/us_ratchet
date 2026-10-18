from copy import deepcopy
import unittest
from scripts import ndx_current99_conditional_price_inventory_20260919 as module


class Tests(unittest.TestCase):
    def fixture(self):
        old=[dict(ticker='T'+str(i),status='CONDITIONAL_PRICE_ARITHMETIC_VERIFIED_NOT_IDENTITY',calendar=['2026-09-16','2026-09-17'],row_count=2) for i in range(95)]
        old.extend(dict(ticker=t,status='EXPLICITLY_BLOCKED_NOT_MISSING_PRICE') for t in ('CMCSA','EXC','HON','LRCX','TRI','WDC'))
        new=[dict(ticker=t,status='POST_ACTION_CONDITIONAL_PRICE_INDEPENDENTLY_AUDITED',calendar=['2026-09-17'],row_count=1) for t in ('EXC','HON','LRCX','WDC')]
        return dict(original_rows=old,post_rows=new)

    def test_99_references_no_original_mutation(self):
        args=self.fixture();before=deepcopy(args);result=module.combine_references(**args)
        self.assertEqual(args,before);self.assertEqual(result['conditional_channels'],99)
        self.assertEqual(result['common_99_provider_calendar'],['2026-09-17'])
        self.assertEqual(result['blocked_channels'],['CMCSA','TRI'])
        self.assertFalse(result['all_99_security_identities_verified'])

    def test_no_partial_extra_or_unaudited_channels(self):
        for mode in ('partial','extra','unaudited','calendar','count'):
            args=self.fixture()
            if mode=='partial':args['post_rows'].pop()
            if mode=='extra':args['post_rows'][0]['ticker']='TRI'
            if mode=='unaudited':args['post_rows'][0]['status']='PRODUCER_ONLY'
            if mode=='calendar':args['post_rows'][0]['calendar']*=2
            if mode=='count':args['post_rows'][0]['row_count']=True
            with self.subTest(mode=mode),self.assertRaises(ValueError):module.combine_references(**args)

    def test_actual_hard_audits_reference_only_inventory(self):
        result=module.build()
        self.assertEqual(result['total_conditional_rows'],107935)
        self.assertEqual(len(result['common_99_provider_calendar']),57)
        self.assertEqual(result['common_99_provider_calendar'][0],'2026-06-29')
        self.assertEqual(result['common_99_provider_calendar'][-1],'2026-09-17')
        self.assertTrue(result['input_artifact_binding_verified'])
        self.assertFalse(result['quote_reconstruction_performed'])
        result['historical_expected_source_hashes'].pop(str(module.Path(module.__file__).resolve()))
        with self.assertRaises(ValueError):module.verify(result)


if __name__=='__main__':unittest.main()
