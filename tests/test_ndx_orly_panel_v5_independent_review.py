"""Producer review using synthetic ORLY numbers only."""
from copy import deepcopy
from decimal import localcontext, Inexact, getcontext
import unittest
from unittest.mock import patch
import test_ndx_new_cutoff_conditional_panel_v5_20260925 as owner

m = owner.m


class Review(unittest.TestCase):
    @classmethod
    def setUpClass(cls): owner.Tests.setUpClass()

    def test_unknown_publication_ein_and_occ_error_never_become_identity(self):
        for attack in ('publication_flag', 'use_action', 'ein', 'occ_identity', 'signature'):
            docs=deepcopy(owner.Tests.docs)
            d=docs['wiring']['v5_extended_provenance'][0]['complete_increment_evidence']
            if attack=='publication_flag': d['publication_date_verified']=True
            elif attack=='use_action': d['action_or_signature_date_used_as_publication']=True
            elif attack=='ein': d['complete_visual_transcription']['ein_used_as_cik']=True
            elif attack=='occ_identity': d['complete_capture_evidence']['occ_failure_is_identity_source']=True
            else: d['signature_date']='2026-03-20'
            with self.subTest(attack=attack),patch.object(m.core,'channel_values') as call:
                with self.assertRaises(ValueError):m.assemble(docs)
                call.assert_not_called()

    def test_low_decimal_context_and_only_orly_call(self):
        def calculate(*args):
            self.assertEqual(args[2],'ORLY');self.assertEqual(getcontext().prec,80)
            self.assertFalse(getcontext().traps[Inexact]);return owner.numbers()
        with localcontext() as context:
            context.prec=2;context.traps[Inexact]=True
            with patch.object(m.core,'channel_values',side_effect=calculate) as call:
                value=m.assemble(owner.Tests.docs)
        self.assertEqual(call.call_count,1)
        self.assertEqual(value['source_coordinate_candidate_count'],24)
        self.assertEqual(value['actual_panel_security_count'],23)
        self.assertEqual(m.codec.typed_decode(value['panel'])['raw_volume'].shape,(63,23))

    def test_old_frame_dtype_proof_rejects_value_equivalent_change(self):
        before=owner.parent();after,_=m.append_orly(before,owner.numbers(),owner.coordinate(),'automotive')
        after['raw_volume']['GOOG']=after['raw_volume']['GOOG'].astype('float64')
        with self.assertRaises(ValueError):m.original_frame_proof(before,after)


if __name__=='__main__':unittest.main()
