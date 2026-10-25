import unittest
from unittest.mock import patch
from fractions import Fraction
from backtest.monthly_exit_core_research_adapter import MonthlyExitCoreResearchAdapter
from backtest import frontier_capped_next_open_research as original
from backtest import historical_dividend_frontier_research as candidate

class FrontierWiringTests(unittest.TestCase):
    def fixture(self):
        days=['2020-01-30','2020-01-31','2020-02-03','2020-02-04','2020-02-05','2020-02-06']
        prices={'A':dict.fromkeys(days,'10')}
        plans=[dict(decision_date=d,search_arguments={'fee_bps':'0'},valuation_quotes=[dict(security_id='A',price='10')],source_hashes={}) for d in [days[0],days[2],days[4]]]
        assembled=dict(session_dates=days,monthly_inputs=plans,close_prices=prices,provider_actions=[],actions=[],cash_stock_merger_events=[],fractional_settlements=None,price_source_references={},distribution_events=[],distribution_fractional_cash_values=None)
        bars={'A':{d:dict(open='10',high='10',low='10',close='10') for d in days}}
        event=dict(event_id='d',security_id='A',ex_date=days[2],payment_date=days[3],amount_per_share='1',withholding_rate='0',assumption='explicit gross research',currency='USD')
        return assembled,bars,event
    def run_module(self,module,events=None):
        assembled,bars,event=self.fixture()
        def select(**kw):
            a=kw['account_state'];equity=Fraction(a['cash'])+10*a['shares'].get('A',0)
            return dict(target_quantities={'A':int(equity/11)},investable_equity=str(equity))
        # Stub only expensive selection/rerank; actual monthly provider, callbacks,
        # execution, affordability and dividend accounting are exercised.
        with patch.object(module,'decide_continuous_guided_for_account',side_effect=select),patch.object(module,'rerank',side_effect=lambda x:x):
            options={} if events is None else {'dividend_events':events}
            return module.run_frontier_capped_next_open(assembled=assembled,ohlc=bars,initial_cash='110',fee_bps='0',slippage_bps='5',max_new_searches=3,risk=MonthlyExitCoreResearchAdapter([]),**options)
    def test_empty_dividend_full_output_parity(self):
        a=self.run_module(original);b=self.run_module(candidate,[])
        self.assertEqual(a,b)
        self.assertEqual(a['status'],'COMPLETE')
        self.assertTrue(any(r.get('event')=='ASSUMED_NEXT_OPEN_FILLED' for r in a['order_log']))
    def test_paid_cash_affects_monthly_sizing_not_receivable(self):
        event=self.fixture()[2]
        result=self.run_module(candidate,[event]);baseline=self.run_module(original)
        self.assertEqual(result['status'],'COMPLETE')
        states=result['selection_account_states'];old=baseline['selection_account_states']
        self.assertEqual(states[1]['account_state'],old[1]['account_state'])
        self.assertEqual(Fraction(states[2]['account_state']['cash'])-Fraction(old[2]['account_state']['cash']),10)
        unknown=dict(event,payment_date=None)
        unpaid=self.run_module(candidate,[unknown])
        self.assertEqual(unpaid['selection_account_states'],baseline['selection_account_states'])
        self.assertEqual(unpaid['daily_ledger'][-1]['dividend_receivable'],'10')
