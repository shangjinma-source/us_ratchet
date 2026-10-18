"""Independent wrapper attacks on synthetic metadata only."""
from copy import deepcopy
from fractions import Fraction
import unittest
from unittest.mock import patch
import test_ndx_new_cutoff_shard_prepare_v6_20260925 as fixture_module
from scripts import ndx_new_cutoff_shard_prepare_v6_20260925 as m

class Tests(unittest.TestCase):
    def test_high_k_certificate_and_zero_allocation_attacks(self):
        self.assertEqual(m.MAX_SHARDS,16000)
        for k in (21,22,23):self.assertGreater(Fraction(k,20),1)
        for offset in (-3,-2,-1):
            for field in ('combination_count','planned_combination_count','planned_canonical_task_count','planned_shard_count'):
                value=fixture_module.synthetic_counts();value['cardinalities'][offset][field]+=1
                with self.subTest(offset=offset,field=field),self.assertRaises(ValueError):m.validate_counts(value)
    def test_authority_and_every_added_evidence_layer(self):
        docs,sources,panel=fixture_module.MetadataTests().fixture()
        for version in (3,4,5,6):
            bad=deepcopy(docs);bad['panel'][f'v{version}_incremental_evidence_and_projection'][0]['early_window_review_availability_verified']=True
            with self.subTest(version=version),patch.object(m.reader,'decode_frames',return_value=panel),self.assertRaises(ValueError):m.inputs_from_documents(bad,sources)
        for role in ('panel','audit'):
            bad=deepcopy(docs);bad[role]['point_in_time_verified']=True
            with patch.object(m.reader,'decode_frames',return_value=panel),self.assertRaises(ValueError):m.inputs_from_documents(bad,sources)
    def test_external_402_does_not_reduce_planned_tasks(self):
        counts=fixture_module.synthetic_counts();counts['remaining_canonical_task_count']-=402
        with self.assertRaises(ValueError):m.validate_counts(counts)
        docs,sources,panel=fixture_module.MetadataTests().fixture();docs['completed_index']['all_plan_tasks_completed']=True
        with patch.object(m.reader,'decode_frames',return_value=panel),self.assertRaises(ValueError):m.inputs_from_documents(docs,sources)
    def test_full_source_and_unknown_publication_stay_fail_closed(self):
        docs,sources,panel=fixture_module.MetadataTests().fixture()
        for attack in ('source','date','ctas_role'):
            bad=deepcopy(docs);closure=dict(sources)
            if attack=='source':closure.pop(next(iter(closure)))
            elif attack=='date':bad['panel']['v5_incremental_evidence_and_projection'][0]['publication_date_verified']=True
            else:bad['panel']['v6_incremental_evidence_and_projection'][0]['dated_anchor_role']='JOINT_AVAILABLE'
            with self.subTest(attack=attack),patch.object(m.reader,'decode_frames',return_value=panel),self.assertRaises(ValueError):m.inputs_from_documents(bad,closure)

if __name__=='__main__':unittest.main()
