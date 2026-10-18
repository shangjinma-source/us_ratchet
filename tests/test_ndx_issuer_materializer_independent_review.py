"""Tiny synthetic slices only; no real panel, task plan, or fitter."""
from copy import deepcopy
import unittest
from unittest.mock import patch
import test_ndx_issuer_task_materialization_research as fixture

m=fixture.m


class IndependentMaterializerReview(unittest.TestCase):
    def test_plan_missing_spec_duplicate_shard_and_false_remaining_rejected_before_slice(self):
        for attack in ('spec','duplicate','remaining','certificate'):
            args=fixture.fixture();plan=args['plan']
            if attack=='spec':plan['context']['weight_specs'].pop()
            elif attack=='duplicate':plan['shards'].append(deepcopy(plan['shards'][0]))
            elif attack=='remaining':plan['remaining_canonical_task_count']=0
            else:plan['cardinalities'][0]['necessary_bound_certificates']=[]
            with self.subTest(attack=attack),patch.object(m.indexing.IssuerCombinationIndex,'slice',side_effect=AssertionError('must not enumerate')):
                with self.assertRaises(ValueError):m.materialize_slice(**args)

    def test_unselected_returns_and_boolean_boundaries_are_prevalidated(self):
        for attack in ('minusone','nan','bool_start','duplicate_date'):
            args=fixture.fixture()
            if attack=='minusone':args['panel']['returns'][0][-1]=-1.
            elif attack=='nan':args['panel']['returns'][0][-1]=float('nan')
            elif attack=='bool_start':args['start']=False
            else:args['panel']['dates'][1]=args['panel']['dates'][0]
            with self.subTest(attack=attack),patch.object(m.indexing.IssuerCombinationIndex,'slice',side_effect=AssertionError('must not enumerate')):
                with self.assertRaises(ValueError):m.materialize_slice(**args)

    def test_location_reference_changes_but_same_numerical_task_is_stable(self):
        first=fixture.fixture();second=fixture.fixture();second['plan_reference']['sha256']='f'*64
        a=m.materialize_slice(**first)['combinations'][0]['tasks']
        b=m.materialize_slice(**second)['combinations'][0]['tasks']
        for old,new in zip(a,b):
            self.assertEqual(old['numerical_task_id'],new['numerical_task_id'])
            self.assertNotEqual(old['location_id'],new['location_id'])
        second=fixture.fixture();second['panel']['universe'][2]['risk_chain']='new_label'
        changed=m.materialize_slice(**second)['combinations'][0]['tasks']
        self.assertTrue(all(x['numerical_task_id']!=y['numerical_task_id'] for x,y in zip(a,changed)))

    def test_full_prior_with_no_survivors_is_kept_for_all_specs_and_empty_slice_is_not_complete(self):
        args=fixture.fixture(prior={'EXIT_A':.5,'EXIT_C':.5})
        result=m.materialize_slice(**args)
        for task in result['combinations'][0]['tasks']:
            self.assertEqual(task['numerical_identity']['requested_previous_target_weights'],{'EXIT_A':.5,'EXIT_C':.5})
            self.assertFalse(task['anchor_alias_equivalence_verified'])
        args.update(start=1,stop=1)
        with patch.object(m.indexing.IssuerCombinationIndex,'unrank') as unrank:
            empty=m.materialize_slice(**args);unrank.assert_not_called()
        self.assertEqual(empty['materialized_task_count'],0)
        self.assertFalse(empty['full_shard_completed']);self.assertFalse(empty['all_plan_tasks_completed'])


if __name__=='__main__':unittest.main()
