from copy import deepcopy
from fractions import Fraction as F
import unittest
from scripts.review_cost_stress_nav_metrics import review


class NavTests(unittest.TestCase):
    def setUp(self):
        self.assembled=dict(session_dates=['2024-12-30','2024-12-31','2025-01-02'],
            price_source_references={'A':['test']},fractional_settlements={},distribution_fractional_cash_values={})
        self.ohlc={'A':{'2024-12-31':{'close':'10'},'2025-01-02':{'close':'8'}}}
        self.outcome=dict(status='COMPLETE',daily_ledger=[dict(date=day,cash='50',shares={'A':5},
            stock_value=stock,equity=equity,external_flow='0',receivable='0',merger_entitlements=[],
            distribution_rights=[],nontradable_entitlement_value='0',distribution_entitlement_value='0')
            for day,stock,equity in [('2024-12-31','50','100'),('2025-01-02','40','90')]])
        self.metrics=dict(final_equity='90',total_return='-1/10',maximum_close_drawdown='1/10',
            cagr=0.9**(365/3)-1,cagr_exact_inputs={'wealth_ratio':'9/10','exponent':'365/3'},
            years=[dict(year=2024,sessions=1,through='2024-12-31',return_fraction='0',maximum_close_drawdown='0'),
                   dict(year=2025,sessions=1,through='2025-01-02',return_fraction='-1/10',maximum_close_drawdown='1/10')])
    def check(self):
        return review(outcome=self.outcome,metrics=self.metrics,assembled=self.assembled,ohlc=self.ohlc,initial_cash='100')
    def test_independent_metrics(self):
        self.assertEqual(self.check()['status'],'SAVED_STATE_NAV_AND_METRICS_VERIFIED')
        self.assertFalse(self.check()['holdings_independently_replayed'])
    def test_tampered_state_components(self):
        for field in ('stock_value','equity','nontradable_entitlement_value'):
            original=deepcopy(self.outcome)
            self.outcome['daily_ledger'][0][field]='123'
            with self.assertRaises(ValueError):self.check()
            self.outcome=original
    def test_year_cagr_and_dates(self):
        self.metrics['years'][1]['return_fraction']='0'
        with self.assertRaisesRegex(ValueError,'ANNUAL'):self.check()
        self.metrics['years'][1]['return_fraction']='-1/10';self.metrics['cagr']=0
        with self.assertRaisesRegex(ValueError,'CAGR'):self.check()
    def test_pending_right_is_revalued_not_trusted(self):
        self.outcome['daily_ledger'][0]['distribution_rights']=[dict(event_id='test',kind='CHILD_PENDING_WHOLE',
            effective_date='2024-12-31',units='1',security_id='A',source_references=['test'])]
        with self.assertRaisesRegex(ValueError,'RIGHTS_VALUATION'):self.check()


if __name__=='__main__':unittest.main()
