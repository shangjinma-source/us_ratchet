"""Independent attacks on hand-built fixtures only, no production materializer."""
from copy import deepcopy
import unittest
import test_ndx_issuer_materialization_independent_readback_research as fixture
m=fixture.m

class IndependentMaterializationReadbackReview(unittest.TestCase):
    def test_false_plan_or_shard_counters_are_not_integer_zero(self):
        for attack in ('plan','shard'):
            args=fixture.fixture()
            target=args['plan'] if attack=='plan' else args['plan']['shards'][0]
            target['completed_canonical_task_count']=False
            with self.subTest(attack=attack),self.assertRaises(ValueError):m.verify_materialized(**args)

    def test_rehashed_task_cannot_substitute_selected_matrix_or_drop_prior(self):
        for attack in ('matrix','prior'):
            args=fixture.fixture({'EXIT_CLASS_A':.6,'a':.4})
            combo=args['value']['combinations'][0]
            if attack=='matrix':
                combo['fit_matrix']['returns'][0][0]=.333
                combo['fit_data_sha256']=m.digest(combo['fit_matrix'])
                for task in combo['tasks']:
                    task['numerical_identity']['fit_data_sha256']=combo['fit_data_sha256']
                    task['numerical_task_id']=m.digest(task['numerical_identity'])
            else:
                for task in combo['tasks']:
                    task['numerical_identity']['requested_previous_target_weights']={'a':1.}
                    task['numerical_task_id']=m.digest(task['numerical_identity'])
            with self.subTest(attack=attack),self.assertRaises(ValueError):m.verify_materialized(**args)

    def test_none_request_and_no_alias_or_completion_are_exact(self):
        for attack in ('none','alias','complete','extra'):
            args=fixture.fixture();task=args['value']['combinations'][0]['tasks'][0]
            if attack=='none':task['numerical_identity']['requested_previous_target_weights']={};task['numerical_task_id']=m.digest(task['numerical_identity'])
            elif attack=='alias':task['anchor_alias_equivalence_verified']=True
            elif attack=='complete':args['value']['all_plan_tasks_completed']=True
            else:args['value']['combinations'][0]['tasks'].append(deepcopy(task))
            with self.subTest(attack=attack),self.assertRaises(ValueError):m.verify_materialized(**args)

if __name__=='__main__':unittest.main()
