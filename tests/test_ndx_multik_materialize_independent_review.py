"""Mock-only batch boundary checks; no real combinations materialized."""
from copy import deepcopy
import unittest
from unittest.mock import patch
import test_ndx_new_cutoff_multik_materialize_20260924 as owner
from scripts import ndx_new_cutoff_multik_materialize_20260924 as m


class IndependentReview(unittest.TestCase):
    def test_prefix_budget_and_none_prior_preserved_in_every_call(self):
        base=owner.base();base['plan']['context']={'previous_target_weights':None}
        arguments=m.batch_arguments(base)
        with patch.object(m.materializer,'materialize_slice',side_effect=owner.stub) as call:
            values=m.materialize_batch(arguments,['4:0:0','4:0:1','4:0:2'])
        self.assertEqual([int(c.kwargs['shard_id']) for c in call.call_args_list],list(range(4,20)))
        self.assertEqual(sum(v['combination_count'] for v in values),31)
        self.assertEqual(sum(v['materialized_task_count'] for v in values),93)
        for c in call.call_args_list:
            self.assertIsNone(c.kwargs['plan']['context']['previous_target_weights'])
            self.assertEqual(c.kwargs['max_materialized_combinations'],c.kwargs['stop']-c.kwargs['start'])

    def test_duplicate_new_identity_across_cardinalities_is_blocked(self):
        def repeated(**argument):
            result=owner.stub(**argument)
            result['combinations'][0]['tasks'][0]['numerical_task_id']='same-cross-k'
            return result
        with patch.object(m.materializer,'materialize_slice',side_effect=repeated) as call:
            with self.assertRaises(ValueError):m.materialize_batch(m.batch_arguments(owner.base()),['old0','old1','old2'])
        self.assertEqual(call.call_count,2)

    def test_skip_old_rank_and_completed_boolean_reject_before_more_dispatch(self):
        args=m.batch_arguments(owner.base());args[0]['start']=0
        with patch.object(m.materializer,'materialize_slice') as call:
            with self.assertRaises(ValueError):m.materialize_batch(args,['a','b','c'])
            call.assert_not_called()
        def false_count(**argument):
            result=owner.stub(**argument);result['completed_task_count']=False;return result
        with patch.object(m.materializer,'materialize_slice',side_effect=false_count) as call:
            with self.assertRaises(ValueError):m.materialize_batch(m.batch_arguments(owner.base()),['a','b','c'])
            self.assertEqual(call.call_count,1)

    def test_source_conflict_cannot_replace_loaded_module(self):
        with self.assertRaisesRegex(ValueError,'conflict'):
            m.guard({str(m.SOURCE):'0'*64})


if __name__=='__main__':unittest.main()
