"""Mock incremental numbers only; never audit the actual CPRT channel."""
from copy import deepcopy
import unittest
from unittest.mock import patch
import test_ndx_new_cutoff_typed_panel_v3_independent_readback_20260925 as owner
from scripts import ndx_new_cutoff_typed_panel_v3_independent_readback_20260925 as m
from scripts import ndx_new_cutoff_conditional_panel_v3_20260925 as producer


class IndependentReview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):owner.Tests.setUpClass()

    def test_mock_producer_envelope_matches_independent_all_fields(self):
        docs=owner.Tests.documents;numbers=owner.Tests.numbers
        with patch.object(producer.core,'channel_values',return_value=numbers) as production:
            candidate=producer.assemble(docs)
        candidate['source_hashes']={}
        with patch.object(m.codec,'channel_numbers',return_value=numbers) as independent:
            result=m.verify_candidate(candidate,docs,{})
        production.assert_called_once();independent.assert_called_once()
        self.assertEqual(result['conditional_security_count'],21)

    def test_rechecksummed_unchanged_gap_cannot_disappear(self):
        helper=owner.Tests();candidate=helper.candidate();panel=m.codec.decode_frames(candidate['panel'])
        row=next(r for r in panel['observed_provenance_and_missing'] if r['ticker']=='CRWD')
        row['blocking_reasons']=[]
        panel['panel_content_sha256']=m.codec.checksum(panel);candidate['panel']=m.codec.encode_frames(panel)
        with self.assertRaises(ValueError):helper.verify(candidate)

    def test_old_and_new_sidecars_cannot_change_class_or_original_risk(self):
        for attack in ('old','new'):
            helper=owner.Tests();candidate=helper.candidate()
            if attack=='old':candidate['original_evidence_and_projection'][0]['ticker']='IMPOSTOR'
            else:candidate['v3_incremental_evidence_and_projection'][0]['complete_extended_provenance']['complete_increment_evidence']['original_business_fact']['assigned_risk_chain']='automotive'
            with self.subTest(attack=attack),self.assertRaises(ValueError):helper.verify(candidate)


if __name__=='__main__':unittest.main()
