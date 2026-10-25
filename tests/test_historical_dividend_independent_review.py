import unittest
from copy import deepcopy
from backtest.historical_dividend_independent_review import review

class AuditTests(unittest.TestCase):
    def fixture(self, unknown=False):
        days=['2020-03-02','2020-03-03','2020-03-04']
        event=dict(event_id='d',security_id='A',ex_date=days[1],payment_date=None if unknown else days[2],amount_per_share='1',withholding_rate='0',assumption='fixture',currency='USD')
        rows=[dict(date=days[1],cash='0',shares={'A':10},stock_value='100',equity='110',dividend_receivable='10'),dict(date=days[2],cash='0' if unknown else '10',shares={'A':10},stock_value='100',equity='110',dividend_receivable='10' if unknown else '0')]
        book=dict(status='COMPLETE',daily_ledger=rows,provider_audit=[{'orders':[]},{'orders':[]}],fee_bps='0',slippage_bps='0',cash=rows[-1]['cash'],shares={'A':10},fees='0',receivable='0',dividend_receivable='10' if unknown else '0',total_receivable='10' if unknown else '0',total_return='1/10',drawdown={'maximum_close_drawdown':'0'},dividend_ledger=dict(events={'d':dict(event=event,net='10')},payments={} if unknown else {'research:d':dict(event_id='d',session_date=days[2])},paid_cash='0' if unknown else '10',receivable='10' if unknown else '0'))
        return dict(book=book,assembled={'session_dates':days,'close_prices':{'A':dict.fromkeys(days,'10')}},bars={'A':{d:dict(open='10',close='10') for d in days}},initial_cash='0',initial_shares={'A':10},dividend_events=[event],verify_selections=False,expected_fee_bps='0',expected_slippage_bps='0')
    def test_paid_and_unknown(self):
        for unknown in (False,True):self.assertEqual(review(**self.fixture(unknown))['final_equity'],'110')
    def test_tampered_cash(self):
        a=self.fixture();a['book']['daily_ledger'][0]['cash']='10'
        with self.assertRaisesRegex(ValueError,'CASH_SHARES'):review(**a)
    def test_tampered_receivable(self):
        a=self.fixture();a['book']['daily_ledger'][0]['dividend_receivable']='0'
        with self.assertRaisesRegex(ValueError,'DIVIDEND_RECEIVABLE'):review(**a)
    def test_duplicate_payment(self):
        a=self.fixture();a['book']['dividend_ledger']['payments']['duplicate']=dict(event_id='d',session_date='2020-03-04')
        with self.assertRaisesRegex(ValueError,'PAYMENT_SET'):review(**a)
    def test_unknown_pay_date_cash(self):
        a=self.fixture(True);a['book']['daily_ledger'][-1]['cash']='10'
        with self.assertRaisesRegex(ValueError,'CASH_SHARES'):review(**a)
    def test_unsupported_action(self):
        a=self.fixture();a['assembled']['actions']=[{}]
        with self.assertRaisesRegex(ValueError,'CORPORATE_ACTION_UNSUPPORTED'):review(**a)

    def test_empty_selection_not_claimed(self):
        a=self.fixture();a['verify_selections']=True
        r=review(**a);self.assertFalse(r['selection_proof_checked']);self.assertEqual(r['selection_proofs_checked'],0)
    def test_terminal_totals(self):
        for k in ('receivable','dividend_receivable','total_receivable'):
            a=self.fixture();a['book'][k]='1'
            with self.assertRaisesRegex(ValueError,'TERMINAL_RECEIVABLES'):review(**a)
    def test_costs_bound_externally(self):
        a=self.fixture();a['book']['fee_bps']='1'
        with self.assertRaisesRegex(ValueError,'EXPECTED_COSTS'):review(**a)
    def test_missing_selection(self):
        a=self.fixture();a['verify_selections']=True;a['assembled']['monthly_inputs']=[{'decision_date':'2020-03-02'}]
        with self.assertRaisesRegex(ValueError,'MISSING_SELECTION_PROOF'):review(**a)
