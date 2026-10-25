"""Independent composition checks; no real account or broker writes."""
import unittest
from core.strategy_account_ledger import create_account, apply_event
from core.strategy_account_difference import build_strategy_difference


class AccountIntegrationTests(unittest.TestCase):
    def setUp(self):self.state=create_account('strategy');self.sequence=0
    def record(self,kind,**fields):
        self.sequence+=1
        if kind in ('FILL','DIRECT_FILL'):fields.setdefault('executed_at','2026-10-16T14:00:00+00:00')
        event=dict(event_id=str(self.sequence),kind=kind,**fields)
        self.state,effect=apply_event(self.state,event,expected_revision=self.state['revision'])
        return event,effect
    def cash(self,amount,basis='TOTAL_UNINVESTED'):
        self.record('CASH_CONFIRM',amount=amount,cash_basis=basis)
    def open(self):
        self.record('ORDER_OPEN',order_id='buy',security_id='A',side='BUY',quantity=6,limit_price='100',fee_per_share='1')
    def preview(self,target=10,legacy=50,targets=None):
        s=self.state;now='2026-10-16T14:00:00+00:00'
        targets={'A':target} if targets is None else targets
        domain={sid for mapping in (s['shares'],targets) for sid,q in mapping.items() if q}
        domain.update(o['security_id'] for o in s['orders'].values() if o['status']=='OPEN')
        return build_strategy_difference(account_id=s['account_id'],account_revision=s['revision'],
            holdings_revision=s['holdings_revision'],cash_confirmed_for_holdings_revision=s['cash_confirmed_for_holdings_revision'],
            cash_balance=s['total_uninvested_cash'],cash_basis='TOTAL_UNINVESTED',strategy_shares=s['shares'],legacy_shares={'A':legacy},
            pending_orders=[o for o in s['orders'].values() if o['status']=='OPEN'],
            marks={sid:dict(security_id=sid,currency='USD',price_basis='CURRENT_UNIT',observed_at=now,price='100') for sid in domain},
            limits={sid:dict(security_id=sid,price_basis='CURRENT_UNIT',observed_at=now,buy='100',sell='100') for sid in domain},
            target_quantities=targets,now=now,maximum_mark_age_seconds=120,fee_bps='0')
    def test_sell_fill_then_confirmed_cash_funds_remaining_target_without_repeat_sell(self):
        self.record('DIRECT_FILL',security_id='A',side='BUY',quantity=14,price='100',fees='0')
        self.cash('100')
        targets={'A':10,'B':5}
        before=self.preview(targets=targets)
        self.assertEqual([(o['side'],o['security_id'],o['quantity']) for o in before['new_orders']],
                         [('SELL','A',4),('BUY','B',1)])
        self.assertEqual(before['waiting_cash'][0]['quantity'],4)
        self.record('DIRECT_FILL',security_id='A',side='SELL',quantity=4,price='100',fees='0')
        self.assertEqual(self.state['shares']['A'],10)
        with self.assertRaisesRegex(ValueError,'CASH_RECONFIRMATION_REQUIRED'):
            self.preview(targets=targets)
        # User supplies the actual broker balance after the sale; no inferred proceeds.
        self.cash('500')
        after=self.preview(targets=targets)
        self.assertEqual([(o['side'],o['security_id'],o['quantity']) for o in after['new_orders']],
                         [('BUY','B',5)])
        self.record('DIRECT_FILL',security_id='B',side='BUY',quantity=5,price='100',fees='0')
        self.cash('0')
        self.assertEqual(self.preview(targets=targets)['new_orders'],[])
    def test_partial_fill_cash_confirmation_pending_and_real_gap(self):
        self.cash('1000');self.open()
        self.record('FILL',order_id='buy',quantity=2,price='99',fees='2')
        with self.assertRaisesRegex(ValueError,'CASH_RECONFIRMATION_REQUIRED'):self.preview()
        self.cash('800')
        result=self.preview()
        self.assertEqual(result['strategy_equity'],'1000')
        self.assertEqual(result['spendable_cash'],'396')
        self.assertEqual(result['new_orders'][0]['quantity'],3)
        self.assertEqual(result['waiting_cash'][0]['quantity'],1)
        self.assertEqual(result['legacy_shares_excluded'],{'A':50})
        self.assertEqual(self.preview(6)['new_orders'],[])
        self.assertEqual(self.preview(1)['status'],'CANCEL_THEN_RECALCULATE')
    def test_available_basis_cancel_matches_total_and_never_sells_legacy(self):
        self.cash('1000');self.open();self.record('FILL',order_id='buy',quantity=2,price='99',fees='2')
        self.cash('396','AVAILABLE_AFTER_RESERVATIONS')
        before=self.preview()
        self.cash('800','TOTAL_UNINVESTED')
        total=self.preview()
        for key in ('strategy_equity','spendable_cash','new_orders','waiting_cash'):
            self.assertEqual(before[key],total[key])
        self.cash('396','AVAILABLE_AFTER_RESERVATIONS');self.record('CANCEL',order_id='buy')
        self.assertEqual(self.preview()['spendable_cash'],'800')
        self.assertEqual(self.preview(0)['new_orders'],[dict(security_id='A',side='SELL',quantity=2,limit_price='100',estimated_cash_change='200')])
    def test_preview_revision_cannot_record_after_concurrent_cash_change(self):
        self.cash('1000');proposal=self.preview();old=proposal['account_revision'];self.cash('900')
        order=dict(event_id='concurrent-order',kind='ORDER_OPEN',order_id='order',security_id='A',side='BUY',quantity=1,limit_price='100',fee_per_share='0')
        with self.assertRaisesRegex(ValueError,'STALE_REVISION'):apply_event(self.state,order,expected_revision=old)


if __name__=='__main__':unittest.main()
