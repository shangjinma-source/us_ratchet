"""Synthetic candidate attacks, never rebuilds the actual new panel."""
from copy import deepcopy
from decimal import localcontext, Inexact, Rounded
import unittest
from unittest.mock import patch
import test_ndx_new_cutoff_typed_panel_independent_readback_20260923 as fixture

m=fixture.m


class IndependentTypedReaderReview(unittest.TestCase):
    def test_full_candidate_sidecar_permissions_and_source_map_are_compared(self):
        expected=dict(panel=m.encode_frames(fixture.panel()),sidecar={'dates':['2023-01-01']},promotion_allowed=False)
        sources={'synthetic':'a'*64}
        original=dict(deepcopy(expected),source_hashes=deepcopy(sources))
        for attack in ('none','sidecar','extra','authority','source'):
            candidate=deepcopy(original)
            if attack=='sidecar':candidate['sidecar']['dates']=[]
            elif attack=='extra':candidate['forged']=True
            elif attack=='authority':candidate['promotion_allowed']=True
            elif attack=='source':candidate['source_hashes']={}
            with self.subTest(attack=attack),patch.object(m,'reconstruct',return_value=deepcopy(expected)) as reconstruct:
                if attack=='none':m.verify_candidate(candidate,{},sources);reconstruct.assert_called_once()
                else:
                    with self.assertRaises(ValueError):m.verify_candidate(candidate,{},sources)
                    if attack=='source':reconstruct.assert_not_called()

    def test_threshold_boundary_and_volume_unit_block_are_distinct(self):
        for volume,expected in ((4999999,'BELOW_ORIGINAL_LIQUIDITY_THRESHOLD'),(5000000,None)):
            c,days=fixture.channel()
            for row in c['price_rows']:row['nominal_close']=10.0
            for row in c['liquidity']['rows']:row.update(raw_volume=volume,dollar_volume=str(10*volume))
            c['liquidity'].update(median_dollar_volume_usd=str(10*volume),numerical_threshold_passed=(volume>=5000000))
            self.assertEqual(m.channel_numbers(c,days)[3],expected)

    def test_nonboolean_types_and_exact_predecessors_required(self):
        for attack in ('volume_bool','close_bool','predecessor','threshold_bool'):
            c,days=fixture.channel()
            if attack=='volume_bool':c['liquidity']['rows'][0]['raw_volume']=True
            elif attack=='close_bool':c['price_rows'][0]['nominal_close']=True
            elif attack=='predecessor':c['price_returns'][50]['previous_session']=days[49]
            else:c['liquidity']['numerical_threshold_passed']=1
            with self.subTest(attack=attack),self.assertRaises(ValueError):m.channel_numbers(c,days)

    def test_ambient_traps_and_tampered_but_rehashed_codec_payload(self):
        c,days=fixture.channel();expected=m.channel_numbers(c,days)
        with localcontext() as context:
            context.prec=2;context.traps[Inexact]=True;context.traps[Rounded]=True
            self.assertEqual(m.channel_numbers(c,days),expected)
        panel=fixture.panel();panel['returns'].iloc[0,0]=1.0
        # The checksum is a mutation checksum, not authority: full comparison rejects it.
        panel['panel_content_sha256']=m.checksum(panel)
        encoded=m.encode_frames(panel)
        candidate={'panel':encoded,'source_hashes':{}}
        with patch.object(m,'reconstruct',return_value={'panel':m.encode_frames(fixture.panel())}):
            with self.assertRaisesRegex(ValueError,'Full typed'):m.verify_candidate(candidate,{}, {})


if __name__=='__main__':unittest.main()
