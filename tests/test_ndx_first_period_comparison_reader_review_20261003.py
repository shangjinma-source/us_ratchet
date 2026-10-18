from copy import deepcopy
import unittest
from unittest.mock import patch
from scripts import ndx_first_period_same_flow_nav_comparison_independent_readback_20261003 as r
from test_ndx_first_period_same_flow_nav_comparison_independent_readback_20261003 import case
from test_ndx_first_period_same_flow_nav_comparison_20261003 import fixture

class ReviewTests(unittest.TestCase):
    def test_real_shape_extended_audit_counts_and_failed_receipt(self):
        docs,refs=fixture()
        docs['incumbent_audit']['counts'].update(executions=12,filled=12,rejected=0,trades=70,quote_references=3408)
        r.check_parent_evidence(docs,refs)
        for mode in ('failed','boolcount','auditsource'):
            bad=deepcopy(docs)
            if mode=='failed':bad['candidate_publication']['status']='FAILED_DO_NOT_CONSUME'
            elif mode=='boolcount':bad['incumbent_audit']['counts']['paths']=True
            else:bad['incumbent_audit']['source_hashes'][refs['incumbent_reader']['path']]='f'*64
            with self.subTest(mode=mode),self.assertRaises(ValueError):r.check_parent_evidence(bad,refs)

    def test_explicit_scope_and_saved_zero_slot_not_lost(self):
        values=case();before=deepcopy(values);self.assertEqual(r.inspect(*values)['independent_metrics'],17)
        self.assertEqual(before,values)
        for mode in ('scope','sameflow','currency','zero'):
            v=deepcopy(values)
            if mode=='scope':v[0]['comparison_scope']='FORMALLY_ELIGIBLE_PIT'
            elif mode=='sameflow':v[0]['rows'][0]['same_flow_timing_and_amount_verified_within_supplied_documents']=1
            elif mode=='currency':v[0]['rows'][0]['currency_scope']='FX_CERTIFIED'
            else:del v[0]['rows'][0]['candidate_saved_selection']['zero_slot_preserved']
            with self.subTest(mode=mode),self.assertRaises(ValueError):r.inspect(*v)

    def test_source_collision_and_decimal_drift(self):
        bad=deepcopy(r.PINS);bad['metrics']=(bad['core'][0],'f'*64)
        with patch.object(r,'PINS',bad),self.assertRaisesRegex(ValueError,'conflict'):r.expected_sources()
        v=case();v[0]['rows'][0]['candidate_minus_incumbent']['annualized_return_diagnostic_decimal']='10000'
        with self.assertRaises(ValueError):r.inspect(*v)

if __name__=='__main__':unittest.main()
