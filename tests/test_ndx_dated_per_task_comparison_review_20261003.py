from copy import deepcopy
from fractions import Fraction as F
import unittest
from backtest import ndx_dated_per_task_comparison_research as m
from test_ndx_dated_per_task_comparison_research import fixture


class Tests(unittest.TestCase):
    def test_integer_path_metrics_independent_pairwise_and_distances(self):
        a=fixture();values=[F(25000)]+[F(25000)+(i%7-3)*F(127)+i*F(19) for i in range(1,127)]
        for row,v in zip(a['candidate_account']['daily'],values):row['total_value_usd']=float(v)
        r=m.compare_per_task_paths(**a);metrics=r['tracks']['candidate_integer']['metrics']
        expected={'cumulative_return':values[-1]/values[0]-1,'annualized_return':(values[-1]/values[0])**2-1,'maximum_drawdown':max(F(0),max(1-values[j]/values[i] for i in range(127) for j in range(i,127)))}
        for key,value in expected.items():self.assertEqual(F(metrics[key]['exact']),value)
        for mode in m.MODES:
            for key in ('annualized_return','maximum_drawdown'):
                nv=F(r['nav_modes'][mode]['metrics'][key]['exact']);iv=F(r['tracks']['incumbent_integer']['metrics'][key]['exact'])
                self.assertEqual(F(r['absolute_distance_comparisons'][mode]['integer'][key]['candidate_minus_incumbent_distance']['exact']),abs(expected[key]-nv)-abs(iv-nv))
        self.assertTrue(all(r[k] is False for k in m.FLAGS))

    def test_unavailable_never_fabricates_cash_or_drops_continuous(self):
        a=fixture();a['candidate_account']=None;a['source_references']['candidate_integer']=None
        a['candidate_integer_status'].update(status='TECHNICAL_MISSING',reason='ORIGINAL_EXCEPTION_RETAINED')
        r=m.compare_per_task_paths(**a);missing=r['tracks']['candidate_integer']
        for key in ('metrics','stored_values_exact','original_account_preserved','source_reference'):self.assertIsNone(missing[key])
        self.assertEqual(missing['missing_evidence'],a['candidate_integer_status'])
        self.assertEqual(r['tracks']['candidate_continuous']['original_track_preserved'],a['candidate_continuous'])
        a['source_references']['candidate_integer']=dict(path='invented',sha256='a'*64,json_pointer='/cash')
        with self.assertRaises(ValueError):m.compare_per_task_paths(**a)

    def test_pointer_and_contract_tamper(self):
        for mutation in (
            lambda a:a['source_references']['candidate_integer'].__setitem__('json_pointer','/bad~2token'),
            lambda a:a['source_references']['candidate_integer'].__setitem__('json_pointer','/'),
            lambda a:a['candidate_integer_status'].__setitem__('status','CASH_FALLBACK'),
            lambda a:a['candidate_continuous'].__setitem__('weights_normalized',True),
            lambda a:a['candidate_account']['decisions'][0].__setitem__('status','NO_PLAN'),
            lambda a:a['nav_metrics']['mode_order'].reverse(),
        ):
            a=fixture();mutation(a)
            with self.assertRaises(ValueError):m.compare_per_task_paths(**a)

if __name__=='__main__':unittest.main()
