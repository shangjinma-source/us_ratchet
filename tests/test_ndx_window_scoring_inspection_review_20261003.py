from copy import deepcopy
import math,unittest
from test_ndx_multidecision_window_scoring_research import fixture
from backtest import ndx_multidecision_window_scoring_research as producer
from backtest import ndx_multidecision_window_scoring_inspection_research as reader

class Review(unittest.TestCase):
    def test_flat_price_closed_form_and_signed_zero(self):
        a,_,_=fixture();a['candidate_returns']=[[0.]*4 for _ in range(504)];a['incumbent_returns']=[0.]*504;a['target_returns']=[0.]*504
        s=producer.reduce_fitted_scoring_windows(**a);row=s['windows'][0]
        self.assertEqual(row['candidate_annualized'],(1-row['entry_cost'])**2-1)
        self.assertEqual(row['candidate_drawdown'],1-(1-row['entry_cost']))
        self.assertEqual(reader.inspect_fitted_scoring_windows(saved_score=s,**a)['status'],'PASS')
        s['windows'][1]['entry_cost']=-0.
        with self.assertRaisesRegex(ValueError,'Binary64'):reader.inspect_fitted_scoring_windows(saved_score=s,**a)

    def test_fee_union_and_single_window_risk_cannot_be_rewritten(self):
        a,_,_=fixture();s=producer.reduce_fitted_scoring_windows(**a)
        for change in (lambda d:d['windows'][0]['fee_summation_order'].append(d['windows'][0]['fee_summation_order'][0]),
                       lambda d:d['windows'][0]['risk_checks'].update(MIN_SINGLE_WEIGHT=1),
                       lambda d:d['windows'][0].update(turnover=math.nextafter(d['windows'][0]['turnover'],math.inf)),
                       lambda d:d.update(fit_performed=True)):
            bad=deepcopy(s);change(bad)
            with self.assertRaises(ValueError):reader.inspect_fitted_scoring_windows(saved_score=bad,**a)

    def test_future_endpoint_and_incomplete_score_rejected(self):
        a,_,_=fixture();s=producer.reduce_fitted_scoring_windows(**a)
        bad=deepcopy(a);bad['fitted_windows'][0]['fit_last_return_end']=a['return_dates'][126]
        with self.assertRaises(ValueError):reader.inspect_fitted_scoring_windows(saved_score=s,**bad)
        s['windows'].pop()
        with self.assertRaises(ValueError):reader.inspect_fitted_scoring_windows(saved_score=s,**a)

if __name__=='__main__':unittest.main()
