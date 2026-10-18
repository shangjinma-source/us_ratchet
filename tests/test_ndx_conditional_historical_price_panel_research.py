import copy
import unittest
import pandas as pd
from backtest import ndx_conditional_historical_price_panel_research as m


def fixture():
    candidate=['LRCX','NFLX']+['C'+str(i) for i in range(12)]
    incumbent=['C0','C1']+['I'+str(i) for i in range(6)]
    calendar=[d.date().isoformat() for d in pd.bdate_range(end='2026-09-17',periods=253)]
    channels={t:dict(nominal_rows=[dict(session=d,open=100.,close=100.) for d in calendar],split_events=[]) for t in set(candidate+incumbent)}
    return dict(calendar=calendar,channels=channels,candidate_tickers=candidate,incumbent_tickers=incumbent,
        minimum_identity_dates={t:'2024-10-03' if t=='LRCX' else None for t in channels},exclude_on_or_after='2026-09-18')


class HistoricalPriceTests(unittest.TestCase):
    def test_nflx_fit_split_boundary_and_real_loss_not_zeroed(self):
        args=fixture();days=args['calendar'];channel=args['channels']['NFLX']
        channel['split_events']=[dict(session=days[50],new_shares=10,old_shares=1,event_kind='ORDINARY_SHARE_SPLIT',raw={'splitRatio':'10:1'})]
        for row in channel['nominal_rows'][50:]:row.update(open=10.,close=10.)
        channel['nominal_rows'][51]['close']=5.
        result=m.assemble_historical_prices(**args)
        self.assertEqual(result['returns'].shape,(252,20));self.assertEqual(result['returns'].loc[days[50],'NFLX'],0.)
        self.assertEqual(result['returns'].loc[days[51],'NFLX'],-.5)
        self.assertEqual(result['fit_return_dates'],days[1:127]);self.assertEqual(result['evaluation_return_dates'],days[127:])
        self.assertEqual(result['submitted_full_split_events']['NFLX'],channel['split_events'])
        self.assertFalse(result['cash_dividends_included']);self.assertTrue(all(r['security_id'] is None for r in result['roles']))

    def test_missing_duplicate_unfinished_or_transition_window_rejected(self):
        for defect in ('missing','duplicate','receipt','floor','future_eval_event'):
            args=fixture();rows=args['channels']['C0']['nominal_rows']
            if defect=='missing':rows.pop(40)
            elif defect=='duplicate':rows.insert(2,copy.deepcopy(rows[1]))
            elif defect=='receipt':args['exclude_on_or_after']=args['calendar'][-1]
            elif defect=='floor':args['minimum_identity_dates']['LRCX']='2026-01-01'
            else:args['channels']['C0']['split_events']=[dict(session=args['calendar'][150],new_shares=2,old_shares=1,event_kind='ORDINARY_SHARE_SPLIT')]
            with self.subTest(defect=defect),self.assertRaises(ValueError):m.assemble_historical_prices(**args)

    def test_positive_ratios_prices_and_complex_actions(self):
        for replacement in (False,0,-1,float('nan'),float('inf')):
            args=fixture();args['channels']['NFLX']['split_events']=[dict(session=args['calendar'][50],new_shares=replacement,old_shares=1,event_kind='ORDINARY_SHARE_SPLIT')]
            with self.assertRaises(ValueError):m.assemble_historical_prices(**args)
        args=fixture();args['channels']['NFLX']['split_events']=[dict(session=args['calendar'][50],new_shares=2,old_shares=1,event_kind='SPINOFF')]
        with self.assertRaises(ValueError):m.assemble_historical_prices(**args)
        args=fixture();args['channels']['C0']['nominal_rows'][0]['open']=False
        with self.assertRaises(ValueError):m.assemble_historical_prices(**args)


if __name__=='__main__':unittest.main()
