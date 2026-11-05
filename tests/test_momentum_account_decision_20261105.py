import unittest
from copy import deepcopy
from unittest.mock import patch
from docs.candidates.momentum_account_decision_20261105 import decide_bound,make_decider

class MomentumCapitalTests(unittest.TestCase):
    def setUp(self):
        self.day='2026-06-30'; securities=[str(i) for i in range(10)]
        self.roster=dict(decision_date=self.day,selected=[dict(security_id=s,issuer_id='issuer'+s) for s in securities],gate=dict(risk_on=True))
        self.args=dict(decision_date=self.day,quote_as_of=self.day,price_basis='NOMINAL_USD',prices={s:'10' for s in securities},metadata={s:dict(issuer_id='issuer'+s,ticker=s) for s in securities},training_scenarios=[{s:'1' for s in securities}],scenario_dates=[self.day],fee_bps='0',minimum_cash_buffer='0')
        self.state=dict(asof=self.day,revision='fixture',cash='100',shares={},reserved_cash='0')
        self.quotes=[dict(security_id=s,price='10',as_of=self.day,price_basis='NOMINAL_USD',source_references=['quote']) for s in securities+['OLD']]
        self.pins={'quote':'a'*64,'backtest/return_priority_fresh_cash_quantity_search.py':'b'*64}

    def call(self):
        with patch('data.current_research_capital_decision.search_fresh_cash_quantities',side_effect=AssertionError('SEARCH_FORBIDDEN')):
            return decide_bound(roster=self.roster,decision_date=self.day,account_state=self.state,valuation_quotes=self.quotes,search_arguments=self.args,source_hashes=self.pins)

    def test_cash_increase_decrease_and_old_holding(self):
        self.assertEqual(self.call()['target_quantities']['0'],1)
        self.state['cash']='200';self.assertEqual(self.call()['target_quantities']['0'],2)
        self.state['cash']='50';self.assertEqual(self.call()['target_quantities']['0'],0)
        self.state.update(cash='0',shares={'OLD':20});result=self.call()
        self.assertEqual(result['investable_equity'],'200');self.assertEqual(result['holding_market_values'],{'OLD':'200'})
        self.assertNotIn('OLD',result['target_quantities']);self.assertEqual(result['search_calls'],0)

    def test_stale_off_and_unsettled(self):
        self.roster['gate']['risk_on']=False;self.assertEqual(self.call()['target_quantities'],{})
        self.quotes[0]['as_of']='2026-06-29'
        with self.assertRaisesRegex(ValueError,'QUOTE_DATE'):self.call()
        self.quotes[0]['as_of']=self.day;self.state['receivables']=[{'amount':'999'}]
        with self.assertRaisesRegex(ValueError,'UNSETTLED_CAPITAL'):self.call()

    def test_real_roster_factory_no_economic_run(self):
        self.assertTrue(callable(make_decider(root='.',window='2021_2023')))
        self.roster['selected'][0]['issuer_id']='wrong'
        with self.assertRaisesRegex(ValueError,'LEGAL_DOMAIN'):self.call()

if __name__=='__main__':unittest.main()
