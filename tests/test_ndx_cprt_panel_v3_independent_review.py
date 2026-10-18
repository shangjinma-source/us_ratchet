"""Saved metadata with mocked CPRT numbers; no actual channel reconstruction."""
from copy import deepcopy
from decimal import localcontext,Inexact,getcontext
import unittest
from unittest.mock import patch
import test_ndx_new_cutoff_conditional_panel_v3_20260925 as f
from scripts import ndx_new_cutoff_conditional_panel_v3_20260925 as m


class IndependentReview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):f.Tests.setUpClass();cls.docs=f.Tests.docs

    def test_only_cprt_call_under_owned_context_and_20_parent_projection(self):
        def numbers(*args):
            self.assertEqual(args[2],'CPRT');self.assertEqual(getcontext().prec,80)
            self.assertFalse(getcontext().traps[Inexact]);return f.numbers()
        with localcontext() as ctx:
            ctx.prec=2;ctx.traps[Inexact]=True
            with patch.object(m.core,'channel_values',side_effect=numbers) as call:
                result=m.assemble(deepcopy(self.docs))
        call.assert_called_once()
        self.assertEqual((result['source_coordinate_candidate_count'],result['actual_panel_security_count'],result['actual_panel_issuer_count']),(22,21,20))
        self.assertEqual(result['original_evidence_and_projection'],self.docs['parent_panel']['original_evidence_and_projection'])
        self.assertEqual(result['incremental_evidence_and_projection'],self.docs['parent_panel']['incremental_evidence_and_projection'])
        self.assertTrue(all(v['exact'] for v in result['original20_frame_exact_proof'].values()))
        self.assertTrue(result['original100_gap_exact']);self.assertTrue(all(result[k] is False for k in m.FALSE))
        self.assertFalse(result['v3_incremental_evidence_and_projection'][0]['early_window_review_availability_verified'])

    def test_old_dtype_change_cannot_pass_frame_proof(self):
        before=f.parent();after,_=m.append_cprt(before,f.numbers(),f.coordinate(),'automotive')
        after['raw_volume']['GOOG']=after['raw_volume']['GOOG'].astype(float)
        with self.assertRaises(ValueError):m.original_frame_proof(before,after)

    def test_full_cprt_original_business_null_and_sidecar_pointer_bound(self):
        for attack in ('business','pointer'):
            docs=deepcopy(self.docs)
            if attack=='business':docs['wiring']['v3_extended_provenance'][0]['complete_increment_evidence']['original_business_fact']['assigned_risk_chain']='automotive'
            else:next(r for r in docs['wiring']['rows'] if r['ticker']=='CPRT')['v3_extended_provenance_reference']['json_pointer']='/v3_extended_provenance/1'
            with patch.object(m.core,'channel_values') as call:
                with self.subTest(attack=attack),self.assertRaises(ValueError):m.assemble(docs)
                call.assert_not_called()


if __name__=='__main__':unittest.main()
