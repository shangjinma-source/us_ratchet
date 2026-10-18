"""Synthetic-only independent queue attacks; no real queue verification."""
import unittest
from unittest.mock import patch
import test_ndx_new_cutoff_ctas_combination_independent_readback_20260925 as fixture
from scripts import ndx_new_cutoff_ctas_combination_independent_readback_20260925 as m

class Tests(unittest.TestCase):
    def test_boolean_coordinates_rejected(self):
        for place in ('start','selection'):
            args=fixture.batch()
            if place=='start':args['materializations'][0]['start']=False
            else:args['selections'][0]['forced_local_rank']=False
            with self.subTest(place=place),patch.object(m.pure,'verify_materialized',return_value={}),self.assertRaises(ValueError):m.validate_materializations(**args)
    def test_old_ids_location_collision_and_shard_overlap(self):
        for attack in ('old_duplicate','location','overlap'):
            args=fixture.batch()
            if attack=='old_duplicate':args['old_ids'][-1]=args['old_ids'][0]
            elif attack=='location':args['materializations'][1]['combinations'][0]['tasks'][0]['location_id']=args['materializations'][0]['combinations'][0]['tasks'][0]['location_id']
            else:args['plan']['shards'].append(dict(args['plan']['shards'][0]))
            with self.subTest(attack=attack),patch.object(m.pure,'verify_materialized',return_value={}),self.assertRaises(ValueError):m.validate_materializations(**args)
    def test_source_conflict_and_missing_anchor_before_io(self):
        with self.assertRaises(ValueError):m.merge({'a':'old'},{'a':'new'})
        with patch.object(m,'PRODUCER_SHA',None),patch.object(m.Path,'read_bytes') as read,self.assertRaises(ValueError):m.build()
        read.assert_not_called()
    def test_prefix_order_and_sameissuer_are_not_sorted_silently(self):
        groups=[dict(issuer_id='A',security_ids=['a','aa']),dict(issuer_id='B',security_ids=['b']),dict(issuer_id='C',security_ids=['c'])]
        for prefix in (['c','a'],['a','aa'],['aa','b']):
            with self.subTest(prefix=prefix),self.assertRaises(ValueError):m.forced_rank(groups,prefix,'a')

if __name__=='__main__':unittest.main()
