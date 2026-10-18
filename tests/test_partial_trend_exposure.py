import unittest
from copy import deepcopy
from test_current_quantity_v2_risk_overlays import fixture as overlay_fixture
from test_current_quantity_v2_risk_next_open import fixture as runner_fixture
from backtest.partial_trend_exposure import partial_sma20_target
from backtest.partial_trend_next_open import run_partial_trend_next_open

class PartialTrendTests(unittest.TestCase):
    def test_odd_floor_equality_and_restored_ceiling(self):
        args=overlay_fixture({'A':[100]*20},quantities={'A':7});before=deepcopy(args)
        self.assertEqual(partial_sma20_target(**args)['target_quantities'],{'A':3})
        self.assertEqual(args,before)
        args['histories']['A']['closes'][-1]['close']='101'
        self.assertEqual(partial_sma20_target(**args)['target_quantities'],{'A':7})
        args['base_target']['quantities']['A']=1;args['histories']['A']['closes'][-1]['close']='100'
        self.assertEqual(partial_sma20_target(**args)['target_quantities'],{'A':0})

    def test_invalid_time_and_units_rejected(self):
        for kind in ('future','before_close','unit'):
            args=overlay_fixture({'A':[100]*20},quantities={'A':7})
            if kind=='future':args['histories']['A']['closes'][-1]['completed_at']='2099-01-01T16:00:00-05:00'
            elif kind=='before_close':args['observed_at']=args['signal_date']+'T15:59:00-05:00'
            else:args['base_target']['price_units']['A']='other-unit'
            with self.assertRaises(ValueError):partial_sma20_target(**args)

    def test_actual_v2_wrapper_half_ceiling_and_future_open_independence(self):
        a,bars,resolver=runner_fixture();progress=[]
        def run(b):return run_partial_trend_next_open(assembled=a,ohlc=b,initial_cash='1000',fee_bps='0',slippage_bps='0',history_resolver=resolver,progress=progress.append)
        out=run(bars);self.assertEqual(out['status'],'COMPLETE')
        audits=out['provider_audit'];ceiling=audits[0]['monthly_ceiling']['A']
        self.assertEqual(audits[1]['target_shares']['A'],ceiling//2)
        self.assertEqual(audits[2]['target_shares']['A'],ceiling)
        self.assertTrue(any(o['side']=='SELL' for o in audits[1]['orders']))
        self.assertTrue(any(o['side']=='BUY' for o in audits[2]['orders']))
        changed=deepcopy(bars);changed['A'][a['session_dates'][1]]=dict(open='999',high='999',low='8',close='8')
        self.assertEqual(run(changed)['provider_audit'][0],audits[0])
        self.assertTrue(any(p.get('event')=='MONTHLY_SEARCH_STARTED' for p in progress))
        self.assertEqual(out['raw_selection_attempts'][0]['target_quantities'],audits[0]['monthly_ceiling'])

    def test_wrapper_rejects_wrong_nominal_units(self):
        a,bars,resolver=runner_fixture()
        def wrong(**kwargs):
            x=resolver(**kwargs);x['histories']['A']['closes'][-1]['close']='999';return x
        out=run_partial_trend_next_open(assembled=a,ohlc=bars,initial_cash='1000',fee_bps='0',slippage_bps='0',history_resolver=wrong)
        self.assertEqual(out['status'],'BLOCKED')
if __name__=='__main__':unittest.main()
