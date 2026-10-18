"""Synthetic multi-k independent reviewer cases; no saved queue readback."""
import unittest
from unittest.mock import patch
import test_ndx_multik_materialization_independent_readback_research as fixture
import test_ndx_new_cutoff_multik_materialization_independent_readback_20260924 as outer_fixture
from backtest import ndx_multik_materialization_independent_readback_research as m


class IndependentReview(unittest.TestCase):
    def test_none_prior_does_not_authorize_spec_alias_or_invented_prior(self):
        for attack in ('alias','prior','duplicate_location'):
            args=fixture.fixture();tasks=args['materializations'][1]['combinations'][0]['tasks']
            if attack=='alias':tasks[2]['anchor_alias_equivalence_verified']=True
            elif attack=='prior':tasks[2]['numerical_identity']['requested_previous_target_weights']={}
            else:tasks[2]['location_id']=tasks[1]['location_id']
            with self.subTest(attack=attack),self.assertRaises(ValueError):m.verify_slices(**args)

    def test_boolean_slice_and_old_coordinates_rejected_before_readback(self):
        for attack in ('new_start','old_rank','old_count'):
            args=fixture.fixture()
            if attack=='new_start':args['materializations'][0]['start']=True
            elif attack=='old_rank':args['old_materialization']['combinations'][0]['rank']=False
            else:args['old_materialization']['combination_count']=True
            with patch.object(m.pure,'verify_materialized') as call:
                with self.subTest(attack=attack),self.assertRaises(ValueError):m.verify_slices(**args)
                call.assert_not_called()

    def test_class_coordinate_cannot_be_merged_by_shared_issuer(self):
        args=fixture.fixture();last=args['materializations'][-1]
        # k19 rank1 differs at the second class of issuer I00.
        self.assertNotEqual(last['combinations'][0]['prefix_security_ids'],last['combinations'][1]['prefix_security_ids'])
        last['combinations'][1]['prefix_security_ids']=last['combinations'][0]['prefix_security_ids'][:]
        with self.assertRaises(ValueError):m.verify_slices(**args)

    def test_external_reference_cannot_relabel_audited_result_or_enable_alias(self):
        for attack in ('status','alias','count'):
            _,docs=outer_fixture.documents_fixture();index=docs['completed_index']
            if attack=='status':index['completed_tasks'][0]['status']='MATERIALIZED_NOT_ATTEMPTED'
            elif attack=='alias':index['anchor_alias_equivalence_verified']=True
            else:index['completed_tasks'][0]['operation_counts']['import_count']=False
            with self.subTest(attack=attack),self.assertRaises(ValueError):outer_fixture.m.reused_reference(docs)


if __name__=='__main__':unittest.main()
