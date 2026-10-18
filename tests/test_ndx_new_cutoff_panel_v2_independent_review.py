"""Synthetic old-frame and metadata attacks; no actual panel build."""
from copy import deepcopy
import unittest
from unittest.mock import patch
import test_ndx_new_cutoff_conditional_panel_v2_20260924 as fixture

m=fixture.m


class IndependentPanelIncrementReview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.docs={k:m.codec.loads((m.BASE/p).read_bytes()) for k,(p,_) in m.BOUND.items()}

    def test_old_frame_dtype_and_calendar_are_part_of_exact_proof(self):
        for attack in ('dtype','date','median'):
            before=fixture.parent();after,_=m.append_pcar(before,fixture.numbers(),fixture.coordinate(),'automotive')
            if attack=='dtype':after['raw_volume']['GOOG']=after['raw_volume']['GOOG'].astype('float64')
            elif attack=='date':after['returns'].index=after['returns'].index+ m.pd.Timedelta(hours=1)
            else:after['universe'].loc[after['universe'].ticker=='GOOG','median_dollar_volume_usd']=42.
            with self.subTest(attack=attack),self.assertRaises(ValueError):m.original_frame_proof(before,after)

    def test_old_null_fact_and_complete_other99_are_required(self):
        for attack in ('null','other99','original_extension','late_date'):
            docs=deepcopy(self.docs)
            if attack=='null':m.one(docs['wiring']['rows'],'PCAR')['complete_original_evidence'][0]['complete_original_fact']['risk_chain']='automotive'
            elif attack=='other99':m.one(docs['wiring']['rows'],'CPRT')['gaps']=[]
            elif attack=='original_extension':m.one(docs['wiring']['extended_provenance'],'PCAR')['original_row']['risk_chain']='automotive'
            else:m.one(docs['wiring']['extended_provenance'],'CRWD')['complete_increment_evidence']['memo_publication_date']='2026-03-20'
            with self.subTest(attack=attack),self.assertRaises(ValueError):m.validate_sources(docs)

    def test_mapping_permissions_and_unknown_sid_rejected_even_with_new_checksum(self):
        panel,_=m.append_pcar(fixture.parent(),fixture.numbers(),fixture.coordinate(),'automotive')
        panel['schema']='LATEST_CONDITIONAL_TYPED_PANEL_V2';panel['panel_content_sha256']=m.core.panel_digest(panel)
        with self.assertRaises(ValueError):m.selected_mapping_v2(panel,['security:missing'])
        panel['legal_training_input_admitted']=True;panel['panel_content_sha256']=m.core.panel_digest(panel)
        with self.assertRaises(ValueError):m.selected_mapping_v2(panel,[fixture.coordinate()['security_id']])

    def test_consumed_bytes_rejected_before_any_increment(self):
        with patch.object(m,'guard'),patch.object(m.Path,'read_bytes',return_value=b'changed'),patch.object(m,'assemble') as assemble:
            with self.assertRaisesRegex(ValueError,'Consumed parent bytes'):m.build()
            assemble.assert_not_called()


if __name__=='__main__':unittest.main()
