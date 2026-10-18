from copy import deepcopy
import unittest
from backtest import ndx_dated_comparison_results_summary_research as m
from test_ndx_dated_comparison_results_summary_research import fixture,saved


class Tests(unittest.TestCase):
    def test_missing_is_not_rejected_cash_or_compressed_domain(self):
        a=fixture()
        for i,options in [(0,{'first':True}),(1,{'missing':True}),(2,{'decision':'NO_PLAN','execution':None}),(33,{'execution':'FILLED'})]:
            t=a['task_summary']['rows'][i];a['comparisons_by_task'][t['numerical_task_id']]=saved(t,**options)
        r=m.summarize_comparisons(**a)
        self.assertEqual(len(r['rows']),1632);self.assertEqual(r['not_supplied_count'],1628)
        self.assertEqual(r['unrepresented_full_domain_count'],6222659648236112666)
        self.assertEqual(sum(x['planned_task_count'] for x in r['k_spec_coverage']),1632)
        self.assertEqual(r['rows'][3]['status'],'NOT_SUPPLIED');self.assertIsNone(r['rows'][3]['tracks'])
        self.assertIsNone(r['rows'][1]['tracks']['candidate_integer']['metrics'])
        self.assertEqual(r['rows'][2]['tracks']['candidate_integer']['execution_statuses'],[])
        self.assertEqual(r['rows'][33]['tracks']['candidate_integer']['execution_statuses'],['FILLED'])
        self.assertTrue(all(r[k] is False for k in m.FLAGS))

    def test_metrics_and_targets_are_copied_without_mode_selection(self):
        a=fixture();t=a['task_summary']['rows'][1];e=saved(t)
        # Deliberately different saved values: aggregation copies, not recomputes.
        for i,mode in enumerate(m.MODES):
            e['document']['comparison']['nav_modes'][mode]['metrics']['annualized_return']['exact']=str(i+3)
            e['document']['comparison']['absolute_distance_comparisons'][mode]['integer']['annualized_return']['candidate_minus_incumbent_distance']['exact']=str(-i-2)
        a['comparisons_by_task'][t['numerical_task_id']]=e;before=deepcopy(a)
        row=m.summarize_comparisons(**a)['rows'][1]
        self.assertEqual(a,before);self.assertEqual(row['original_targets'],e['original_targets'])
        self.assertEqual([row['nav_modes'][mode]['nav_metrics']['annualized_return']['exact'] for mode in m.MODES],['3','4'])
        self.assertEqual([row['nav_modes'][mode]['absolute_distance_comparisons']['integer']['annualized_return']['candidate_minus_incumbent_distance']['exact'] for mode in m.MODES],['-2','-3'])

    def test_stratum_metric_and_fake_missing_attacks(self):
        a=fixture();a['task_summary']['rows'][0]['weight_spec']=m.SPECS[1]
        with self.assertRaises(ValueError):m.summarize_comparisons(**a)
        for mutation in (
            lambda e:e['document']['comparison']['tracks']['candidate_integer']['metrics']['annualized_return'].__setitem__('exact','0.0'),
            lambda e:e['document']['comparison']['tracks']['candidate_integer']['original_account_preserved'].__setitem__('decisions',[{'status':'NO_PLAN'}]),
            lambda e:e['document']['comparison']['tracks']['candidate_integer'].__setitem__('status','MISSING_ASSUMED_CASH'),
            lambda e:e['audit'].__setitem__('formal_comparison_passed',0),
        ):
            a=fixture();t=a['task_summary']['rows'][1];e=saved(t);mutation(e);a['comparisons_by_task'][t['numerical_task_id']]=e
            with self.assertRaises(ValueError):m.summarize_comparisons(**a)

if __name__=='__main__':unittest.main()
