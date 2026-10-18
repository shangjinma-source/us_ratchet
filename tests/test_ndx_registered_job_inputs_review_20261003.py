from copy import deepcopy
from fractions import Fraction
import unittest
from backtest import ndx_registered_scoring_job_inputs_research as core
from test_ndx_registered_scoring_job_inputs_research import fixture


class Review(unittest.TestCase):
    def test_nonzero_union_offset_copies_only_registered_504_rows(self):
        args=fixture();expected=[]
        for column,binding in enumerate(args['channel_bindings']):
            channel=binding['channel'];rows=channel['return_rows']
            for n,row in enumerate(rows):
                value=Fraction((column+1)*(n+1),10000000)
                row.update(split_only_return_exact=str(value),split_only_return_float=float(value))
            expected.append([row['split_only_return_float'] for row in rows])
            channel['return_rows']=[{'outside_selected_window':True}]*3+rows+[{'outside_selected_window':True}]
            decision=channel['decisions'][0];decision.update(price_index_start=3,price_index_stop=508)
            for window in decision['windows']:
                for key in ('training_return_index_start','training_return_index_stop','evaluation_return_index_start','evaluation_return_index_stop'):window[key]+=3
        out=core.assemble_registered_scoring_job_inputs(**args)
        self.assertEqual(out['rolling_inputs']['candidate_returns'],[list(row) for row in zip(*expected)])
        self.assertEqual(out['reducer_inputs']['candidate_returns'],out['rolling_inputs']['candidate_returns'])
        self.assertEqual(len(out['rolling_inputs']['candidate_returns']),504)
        self.assertFalse(out['dispatch_authorized'])

    def test_resigned_prior_and_typed_rank_do_not_change_registered_semantics(self):
        for field,value in [('internal_initial_previous_weights',{}),('outer_lane_prior_applied',0)]:
            args=fixture();job=args['registered_job'];job['identity'][field]=value;job['job_id']=core.digest(job['identity'])
            with self.assertRaises(ValueError):core.assemble_registered_scoring_job_inputs(**args)
        args=fixture();args['registered_job']['position']['rank']=True
        with self.assertRaises(ValueError):core.assemble_registered_scoring_job_inputs(**args)
        args=fixture();args['channel_bindings'][0]['channel']['return_rows'][0]['split_only_return_exact']='0'
        with self.assertRaises(ValueError):core.assemble_registered_scoring_job_inputs(**args)

    def test_original_weight_total_overflow_cannot_be_normalized_to_zero(self):
        args=fixture();original=args['original8_inputs']
        for row in original['original_control_preserved']['securities']:row['target_weight']=1e308
        original['normalized_scoring_weights']={f'C{i}':0.0 for i in range(8)}
        with self.assertRaises(ValueError):core.assemble_registered_scoring_job_inputs(**args)


if __name__=='__main__':unittest.main()
