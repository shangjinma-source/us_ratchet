import tempfile
import unittest
from pathlib import Path
from fractions import Fraction
from api.strategy_account import StrategyAccountService
from data.roa_cash_flow.audit import audit_cash_changes

class CorrectionTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        self.service=StrategyAccountService(database_path=Path(self.directory.name)/'account.db',account_id='test',resolver=None)
        self.store=self.service.store;self.store.initialize('test',operation_id='init')
        self.add('CASH_CONFIRM',amount='10000',cash_basis='TOTAL_UNINVESTED')
        self.fill=self.add('DIRECT_FILL',security_id='AAPL',side='BUY',quantity=11,price='334.77',fees='0',executed_at='2026-11-06T16:00:00+00:00')
    def add(self,kind,**fields):
        state=self.store.read();event=dict(kind=kind,event_id=str(len(state['events'])+1),**fields)
        self.store.append(event,expected_revision=state['revision']);return event
    def correct(self,**changes):
        event=dict(kind='FILL_PRICE_CORRECTION',event_id='repair',fill_id=self.fill['event_id'],previous_price='334.77',price='344.77',reason='User confirmed typo')
        event.update(changes)
        return self.service.append(dict(expected_revision=self.store.read()['revision'],event=event))
    def test_real_journal_unchanged_and_projection_correct(self):
        self.add('CASH_CONFIRM',amount='1552.25',cash_basis='TOTAL_UNINVESTED')
        before=self.store.read();raw=self.store.path.read_bytes()
        result=self.correct()['account']
        self.assertEqual(self.store.read(),before);self.assertEqual(self.store.path.read_bytes(),raw)
        self.assertEqual(result['holdings'][0]['quantity'],11)
        self.assertEqual(Fraction(result['holding_costs'][0]['total_cost']),Fraction('3792.47'))
        self.assertEqual(Fraction(result['cash']),Fraction('1552.25'))
        self.assertEqual(len(result['fills']),1)
        self.assertEqual(result['fills'][0]['executed_at'],self.fill['executed_at'])
    def test_cash_reconciliation_uses_corrected_trade(self):
        baseline=self.store.read()
        self.add('CASH_CONFIRM',amount='6207.53',cash_basis='TOTAL_UNINVESTED')
        self.assertEqual(audit_cash_changes(baseline=baseline,current=self.service.audit_state())['confirmations'][0]['unexplained_net_change'],'-110')
        self.correct()
        self.assertEqual(audit_cash_changes(baseline=baseline,current=self.service.audit_state())['confirmations'][0]['unexplained_net_change'],'0')
    def test_idempotent_retry_and_stale_price(self):
        first=self.correct();self.assertEqual(self.correct(),first)
        with self.assertRaisesRegex(ValueError,'STALE_FILL_PRICE'):self.correct(event_id='next',price='345.77')
        with self.assertRaisesRegex(ValueError,'EVENT_ID_CONFLICT'):self.correct(price='345.77')
        result=self.correct(event_id='next',previous_price='344.77',price='345.77')
        self.assertEqual(Fraction(result['account']['fills'][0]['price']),Fraction('345.77'))
    def test_invalid_request_does_not_create_sidecar(self):
        self.assertFalse(self.service.corrections.path.exists())
        with self.assertRaisesRegex(ValueError,'UNKNOWN_FILL'):self.correct(fill_id='missing')
        self.assertFalse(self.service.corrections.path.exists())
    def test_stale_account_rejected_without_sidecar(self):
        event=dict(kind='FILL_PRICE_CORRECTION',event_id='repair',fill_id=self.fill['event_id'],previous_price='334.77',price='344.77',reason='correction')
        with self.assertRaisesRegex(ValueError,'STALE_REVISION'):
            self.service.append(dict(expected_revision='0'*64,event=event))
        self.assertFalse(self.service.corrections.path.exists())
    def test_linked_partial_fill_preserves_remaining_order(self):
        self.add('ORDER_OPEN',order_id='buy',security_id='TXN',side='BUY',quantity=10,limit_price='100',fee_per_share='0')
        fill=self.add('FILL',order_id='buy',quantity=3,price='99',fees='0',executed_at='2026-11-06T17:00:00+00:00')
        before=self.store.read()
        result=self.correct(fill_id=fill['event_id'],previous_price='99',price='98')['account']
        self.assertEqual(self.store.read(),before)
        self.assertEqual(result['orders'][0]['remaining_quantity'],7)
        self.assertEqual(Fraction(result['fills'][-1]['price']),98)

    def test_http_correction_and_stale_price_conflict(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from api.strategy_account import create_router
        app=FastAPI();app.include_router(create_router(database_path=self.store.path,account_id='test',resolver=None))
        with TestClient(app) as client:
            event=dict(kind='FILL_PRICE_CORRECTION',event_id='http-repair',fill_id=self.fill['event_id'],previous_price='334.77',price='344.77',reason='User confirmed typo')
            response=client.post('/api/strategy-account/events',json=dict(expected_revision=self.store.read()['revision'],event=event))
            self.assertEqual(response.status_code,200)
            self.assertEqual(Fraction(client.get('/api/strategy-account').json()['account']['fills'][0]['price']),Fraction('344.77'))
            event.update(event_id='stale',price='345.77')
            self.assertEqual(client.post('/api/strategy-account/events',json=dict(expected_revision=self.store.read()['revision'],event=event)).status_code,409)

    def test_following_fill_cash_confirmation_and_restart_preserve_correction(self):
        self.correct()
        self.service.resolver=lambda ticker:dict(ticker=ticker,security_id='AAPL',source_references=['test'],source_hashes={'test':'a'*64})
        sell=dict(kind='DIRECT_FILL',event_id='subsequent-sale',ticker='AAPL',side='SELL',quantity=5,price='350',fees='0',executed_at='2026-11-06T17:00:00+00:00')
        response=self.service.append(dict(expected_revision=self.store.read()['revision'],event=sell))
        self.assertFalse(response['account']['cash_confirmation_valid'])
        self.assertEqual(Fraction(response['account']['holding_costs'][0]['total_cost']),6*Fraction('344.77'))
        baseline=self.service.store.read()
        expected_cash=10000-11*Fraction('344.77')+5*350
        self.service.append(dict(expected_revision=baseline['revision'],event=dict(kind='CASH_CONFIRM',event_id='subsequent-cash',amount=str(expected_cash),cash_basis='TOTAL_UNINVESTED')))
        reopened=StrategyAccountService(database_path=self.store.path,account_id='test',resolver=None)
        account=reopened.read()['account']
        self.assertTrue(account['cash_confirmation_valid'])
        self.assertEqual(Fraction(account['cash']),expected_cash)
        self.assertEqual(Fraction(account['fills'][0]['price']),Fraction('344.77'))
        self.assertEqual(len(account['fills']),2)
        self.assertEqual(audit_cash_changes(baseline=baseline,current=reopened.audit_state())['confirmations'][0]['unexplained_net_change'],'0')

    def test_partial_sale_and_unconfirmed_cash(self):
        self.add('DIRECT_FILL',security_id='AAPL',side='SELL',quantity=5,price='350',fees='0',executed_at='2026-11-06T17:00:00+00:00')
        result=self.correct()['account']
        self.assertEqual(result['holdings'][0]['quantity'],6)
        self.assertEqual(Fraction(result['holding_costs'][0]['total_cost']),6*Fraction('344.77'))
        self.assertFalse(result['cash_confirmation_valid'])
        self.assertEqual(Fraction(result['cash_summary']['derived_total_uninvested_cash_estimate']),10000-11*Fraction('344.77')+1750)

if __name__=='__main__':unittest.main()
