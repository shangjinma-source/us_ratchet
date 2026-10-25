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


class SplitDividendAuditTests(unittest.TestCase):
    def fixture(self):
        from backtest.historical_dividend_next_open_book_research import run_next_open_book
        days=['2020-03-02','2020-03-03','2020-03-04']
        split=dict(date=days[1],security_id='A',type='split',new_shares=2,old_shares=1,source_references=['synthetic-split'])
        dividend=dict(event_id='d',security_id='A',ex_date=days[2],payment_date=days[2],amount_per_share='1',withholding_rate='0',assumption='fixture',currency='USD')
        bars={'A':{d:dict(open='5',high='5',low='5',close='5') for d in days[1:]}}
        orders=[dict(id='s',security_id='A',side='SELL',quantity=1,decision_mark='10',decision_date=days[0],active_date=days[1]),dict(id='b',security_id='A',side='BUY',quantity=2,decision_mark='5',decision_date=days[1],active_date=days[2])]
        audits=[]
        def provider(**kw):
            r=dict(status='READY',orders=[o for o in orders if o['active_date']==kw['active_date']]);audits.append(deepcopy(r));return r
        book=run_next_open_book(session_dates=days,order_provider=provider,ohlc=bars,initial_cash='10',initial_shares={'A':10},events=[split],fee_bps='0',slippage_bps='0',dividend_events=[dividend])
        book.update(provider_audit=audits,total_return='9/55',drawdown={'maximum_close_drawdown':'0'})
        return dict(book=book,assembled=dict(session_dates=days,close_prices={'A':{days[0]:'10'}},actions=[split],provider_actions=[deepcopy(split)]),bars=bars,initial_cash='10',initial_shares={'A':10},dividend_events=[dividend],verify_selections=False,expected_fee_bps='0',expected_slippage_bps='0')
    def test_nonempty_split_sell_dividend_buy(self):
        args=self.fixture();result=review(**args)
        self.assertEqual(result['final_equity'],'128')
        self.assertEqual(result['ordinary_splits_checked'],1)
        self.assertEqual(args['book']['cash'],'28')
        self.assertEqual(args['book']['dividend_ledger']['paid_cash'],'18')
    def test_wrong_split_ratio_or_missing_source_rejected(self):
        for field,value in [('new_shares',3),('source_references',[])]:
            args=self.fixture();args['assembled']['actions'][0][field]=value
            args['assembled']['provider_actions']=deepcopy(args['assembled']['actions'])
            with self.assertRaises(ValueError):review(**args)
    def test_same_day_dividend_rejected(self):
        args=self.fixture();args['dividend_events'][0]['ex_date']='2020-03-03'
        with self.assertRaisesRegex(ValueError,'SAME_DAY'):review(**args)
    def test_fractional_split_cash_never_invented(self):
        args=self.fixture();args['assembled']['actions'][0]['old_shares']=3
        args['assembled']['provider_actions']=deepcopy(args['assembled']['actions'])
        with self.assertRaisesRegex(ValueError,'FRACTIONAL_SPLIT_HOLDING'):review(**args)
    def test_unadjusted_order_tamper_rejected(self):
        args=self.fixture();args['book']['provider_audit'][0]['orders'][0]['quantity']=2
        with self.assertRaises(ValueError):review(**args)
