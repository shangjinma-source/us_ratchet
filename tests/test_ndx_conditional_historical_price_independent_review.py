"""Independent temporal/unit checks; synthetic data, no fit or I/O."""
import copy
import unittest
from datetime import date,timedelta
from test_ndx_conditional_historical_price_panel_research import fixture
from backtest import ndx_conditional_historical_price_panel_research as m


class HistoricalInputIndependentReview(unittest.TestCase):
    def test_share_ratio_preserves_market_move_and_reverse_split(self):
        args=fixture();days=args['calendar'];channel=args['channels']['NFLX']
        channel['split_events']=[dict(session=days[30],new_shares=10,old_shares=1,event_kind='ORDINARY_SHARE_SPLIT'),dict(session=days[40],new_shares=1,old_shares=5,event_kind='ORDINARY_SHARE_SPLIT')]
        for row in channel['nominal_rows'][30:40]:row.update(open=10.1,close=10.1)
        for row in channel['nominal_rows'][40:]:row.update(open=50.5,close=50.5)
        result=m.assemble_historical_prices(**args)
        self.assertAlmostEqual(result['returns'].loc[days[30],'NFLX'],.01,places=14)
        self.assertEqual(result['returns'].loc[days[40],'NFLX'],0.)

    def test_positive_decimal_price_underflow_must_not_emit_zero_float_prices(self):
        args=fixture()
        for row in args['channels']['C0']['nominal_rows']:row.update(open='1e-400',close='1e-400')
        with self.assertRaises(ValueError):m.assemble_historical_prices(**args)

    def test_omitted_observed_session_and_first_forward_split_rejected(self):
        for defect in ('omitted','boundary'):
            args=fixture();days=args['calendar'];channel=args['channels']['C0']
            if defect=='boundary':
                channel['split_events']=[dict(session=days[127],new_shares=2,old_shares=1,event_kind='ORDINARY_SHARE_SPLIT')]
            else:
                previous=next(a for a,b in zip(days,days[1:]) if (date.fromisoformat(b)-date.fromisoformat(a)).days>1)
                extra=(date.fromisoformat(previous)+timedelta(days=1)).isoformat()
                channel['nominal_rows'].append(dict(session=extra,open=100.,close=100.))
                channel['nominal_rows'].sort(key=lambda r:r['session'])
            with self.subTest(defect=defect),self.assertRaises(ValueError):m.assemble_historical_prices(**args)

    def test_latest_weights_cannot_be_consumed_as_historical_fit(self):
        args=fixture();args['latest_cutoff_weights']={'NFLX':1.}
        with self.assertRaises(TypeError):m.assemble_historical_prices(**args)
        args=fixture();args['channels']['NFLX']['checkpoint_weights']={'NFLX':1.}
        with self.assertRaises(ValueError):m.assemble_historical_prices(**args)


if __name__=='__main__':unittest.main()
