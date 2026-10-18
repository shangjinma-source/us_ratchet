from copy import deepcopy
import unittest
from test_ndx_multidecision_window_scoring_research import fixture
from backtest import ndx_multidecision_window_scoring_research as m

class Review(unittest.TestCase):
    def test_flat_returns_fee_has_independent_closed_form(self):
        a,_,_=fixture();a['candidate_returns']=[[0.]*4 for _ in range(504)];a['incumbent_returns']=[0.]*504;a['target_returns']=[0.]*504
        r=m.reduce_fitted_scoring_windows(**a);first=r['windows'][0]
        turnover=.5*sum(abs(.25-first['fee_reference_weights'][x]) if x in 'ABCD' else first['fee_reference_weights'][x] for x in first['fee_summation_order'])
        cost=turnover*.001
        self.assertEqual(first['entry_cost'],cost)
        self.assertEqual(first['candidate_annualized'],(1-cost)**2-1)
        self.assertEqual(first['candidate_drawdown'],1-(1-cost))
        self.assertTrue(all(x['entry_cost']==0 and x['candidate_annualized']==0 for x in r['windows'][1:]))
        self.assertFalse(r['whole_lot_gate_evaluated'])

    def test_single_minimum_violation_not_hidden_by_other_windows(self):
        a,_,_=fixture();a['securities'].append(dict(security_id='E',ticker='E',issuer_id='E',risk_chain='E'))
        for row in a['candidate_returns']:row.append(0.)
        for w in a['fitted_windows']:w['weights']=[.2]*5
        a['fitted_windows'][6]['weights']=[.24,.24,.24,.24,.04]
        r=m.reduce_fitted_scoring_windows(**a)
        self.assertFalse(r['fractional_risk_passed'])
        self.assertEqual([k for k,v in r['windows'][6]['risk_checks'].items() if not v],['MIN_SINGLE_WEIGHT'])
        self.assertTrue(all(all(w['risk_checks'].values()) for i,w in enumerate(r['windows']) if i!=6))

    def test_aggregate_overflow_and_causal_endpoint_rejected(self):
        a,_,_=fixture();a['original_incumbent_weights']=dict.fromkeys('ABCDEFGH',1e308)
        with self.assertRaises(ValueError):m.reduce_fitted_scoring_windows(**a)
        a,_,_=fixture();a['fitted_windows'][-1]['fit_last_return_end']=a['return_dates'][-1]
        with self.assertRaises(ValueError):m.reduce_fitted_scoring_windows(**a)

if __name__=='__main__':unittest.main()
