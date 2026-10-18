from copy import deepcopy
import unittest
from unittest.mock import patch
from scripts import ndx_dated_per_task_comparison_independent_readback_20261003 as reader
from backtest import ndx_dated_per_task_comparison_research as producer
from test_ndx_dated_per_task_comparison_research import fixture

def verify(args,result):
    return reader.inspect(result,dict(candidate=args['candidate_account'],incumbent=args['incumbent_account']),dict(candidate=args['candidate_continuous'],incumbent=args['incumbent_continuous']),args['nav_metrics'],args['source_references'],args['candidate_integer_status'])

class Tests(unittest.TestCase):
    def test_full_and_actual_cash_are_distinct_from_missing(self):
        a=fixture();out=producer.compare_per_task_paths(**a);counts=verify(a,out)
        self.assertEqual(counts['path_count'],6);self.assertEqual(counts['observation_count'],762);self.assertEqual(counts['available_distance_cell_count'],8)
        for r in a['candidate_account']['daily']:r.update(total_value_usd=25000.,cash_usd=25000.,shares={})
        a['candidate_account']['decisions'][0]['status']='NO_PLAN';a['candidate_account']['executions']=[]
        out=producer.compare_per_task_paths(**a);self.assertEqual(verify(a,out)['path_count'],6)

    def test_absent_integer_does_not_invent_zero_metrics(self):
        a=fixture();a['candidate_account']=None;a['source_references']['candidate_integer']=None;a['candidate_continuous']['positions_preserved'][0]['target_weight']=0.
        a['candidate_integer_status'].update(status='NOT_EXECUTED_NONPOSITIVE_TARGET',reason='Saved zero input')
        out=producer.compare_per_task_paths(**a);c=verify(a,out);self.assertEqual(c['path_count'],5);self.assertEqual(c['observation_count'],635);self.assertEqual(c['available_distance_cell_count'],4)
        bad=deepcopy(out);bad['tracks']['candidate_integer']['metrics']={}
        with self.assertRaises(ValueError):verify(a,bad)

    def test_arithmetic_source_and_formal_tampering(self):
        a=fixture();out=producer.compare_per_task_paths(**a)
        for mutate in (lambda r:r['tracks']['candidate_integer']['metrics']['annualized_return'].update(exact='0'),lambda r:r['tracks']['candidate_continuous']['stored_values_exact'].__setitem__(40,'999'),lambda r:r['source_references_preserved']['candidate_continuous'].update(json_pointer='/tracks/incumbent'),lambda r:r.update(formal_comparison_passed=0),lambda r:r['source_hash_claims'].clear(),lambda r:r['tracks']['candidate_integer']['metrics']['drawdown'].update(peak_index=True)):
            bad=deepcopy(out);mutate(bad)
            with self.assertRaises(ValueError):verify(a,bad)

    def test_pending_producer_pin_fails_closed(self):
        with patch.object(reader,'PRODUCER_SHA',None),self.assertRaises(ValueError):reader.guard({})

if __name__=='__main__':unittest.main()
