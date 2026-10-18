"""Independent exact distance, all-cash and separate-reference counterexamples."""
from fractions import Fraction as F
from copy import deepcopy
import unittest
import test_ndx_dated_economic_comparison_research as owner
m=owner.core


class Review(unittest.TestCase):
    def test_independent_all_pairs_metrics_and_each_mode_distances(self):
        a=owner.fixture_comparison();other=a['nav_metrics']['modes'][m.MODES[1]]
        for row in other['observations']:row.update(saved_value_exact='1',normalized_value_exact='1')
        for row in other['interval_returns']:row['return_exact']='0'
        for key in ('cumulative_return','annualized_return','maximum_drawdown'):other['metrics'][key]['exact']='0'
        # Oscillating account path tests a later peak, without touching accounting.
        values=[25000]+[24000+(i%9)*500 for i in range(125)]+[26000]
        for row,v in zip(a['candidate_account']['daily'],values):row['total_value_usd']=v
        r=m.compare_dated_paths(**a);v=[F(x,25000) for x in values]
        ann=v[-1]**2-1;dd=max(1-v[j]/v[i] for i in range(127) for j in range(i,127))
        self.assertEqual(F(r['tracks']['candidate_integer']['metrics']['annualized_return']['exact']),ann)
        self.assertEqual(F(r['tracks']['candidate_integer']['metrics']['maximum_drawdown']['exact']),dd)
        for mode,nava,navd in [(m.MODES[0],F(11,25),F(1,5)),(m.MODES[1],F(0),F(0))]:
            d=r['absolute_distance_comparisons'][mode]['integer']
            self.assertEqual(F(d['annualized_return']['candidate_minus_incumbent_distance']['exact']),abs(ann-nava)-abs(nava))
            self.assertEqual(F(d['maximum_drawdown']['candidate_minus_incumbent_distance']['exact']),abs(dd-navd)-abs(navd))
        self.assertTrue(all(r[k] is False for k in m.FLAGS))

    def test_rejected_cash_path_is_not_discarded_or_charged_fractional_fee(self):
        a=owner.fixture_comparison();account=a['candidate_account'];account['executions'][0]['status']='REJECTED'
        for row in account['daily']:row.update(cash_usd=25000.,total_value_usd=25000.,shares={})
        before=deepcopy(a);r=m.compare_dated_paths(**a)
        self.assertEqual(a,before)
        for key in ('cumulative_return','annualized_return','maximum_drawdown'):self.assertEqual(r['tracks']['candidate_integer']['metrics'][key]['exact'],'0')
        self.assertNotEqual(r['tracks']['candidate_continuous']['metrics']['cumulative_return']['exact'],'0')
        self.assertEqual(r['saved_paths_preserved']['candidate']['integer_account']['executions'][0]['status'],'REJECTED')

    def test_saved_interval_or_permission_and_class_identity_tamper_rejected(self):
        for kind in ('interval','issuer','flag','date'):
            a=owner.fixture_comparison()
            if kind=='interval':a['nav_metrics']['modes'][m.MODES[1]]['interval_returns'][-1]['return_exact']='123'
            elif kind=='issuer':a['candidate_account']['decisions'][0]['targets']['candidate0']['issuer_id']='wrong'
            elif kind=='flag':a['continuous_document']['point_in_time_verified']=0
            else:a['continuous_document']['tracks']['candidate']['path'][-1]['session']='2026-09-22'
            with self.assertRaises(ValueError):m.compare_dated_paths(**a)


if __name__=='__main__':unittest.main()
