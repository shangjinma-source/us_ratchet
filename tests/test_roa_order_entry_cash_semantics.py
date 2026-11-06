"""Real isolated HTTP order/fill/cancel ledger cash semantics."""
from tempfile import TemporaryDirectory
from pathlib import Path
from datetime import datetime,timezone
import unittest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.strategy_account import create_router
class OrderCashAudit(unittest.TestCase):
 def test_available_basis_partial_fill_cancel_and_idempotency(self):
  with TemporaryDirectory() as folder:
   app=FastAPI();app.include_router(create_router(database_path=Path(folder)/'account.sqlite3',account_id='test',resolver=lambda t:dict(ticker=t,security_id='X',source_references=['synthetic'],source_hashes={'synthetic':'a'*64}),clock=lambda:datetime(2026,11,6,16,tzinfo=timezone.utc)))
   with TestClient(app) as c:
    self.assertEqual(c.post('/api/strategy-account/initialize',json={'event_id':'init'}).status_code,200)
    def state():return c.get('/api/strategy-account').json()['account']
    def event(e):
     body={'expected_revision':state()['revision'],'event':e};r=c.post('/api/strategy-account/events',json=body);self.assertEqual(r.status_code,200,r.text);return body,r.json()['account']
    event(dict(event_id='cash0',kind='CASH_CONFIRM',amount='1000',cash_basis='AVAILABLE_AFTER_RESERVATIONS'))
    body,a=event(dict(event_id='order',kind='ORDER_OPEN',order_id='broker1',ticker='X',side='BUY',quantity=4,limit_price='100',fee_per_share='0'));self.assertFalse(a['cash_confirmation_valid'])
    self.assertEqual(c.post('/api/strategy-account/events',json=body).json()['account']['revision'],a['revision'])
    _,a=event(dict(event_id='cash1',kind='CASH_CONFIRM',amount='600',cash_basis='AVAILABLE_AFTER_RESERVATIONS'));self.assertEqual((a['available_cash'],a['reserved_cash'],a['total_uninvested_cash']),('600','400','1000'))
    conflict=dict(body,expected_revision=a['revision'],event=dict(body['event'],event_id='other'))
    duplicate=c.post('/api/strategy-account/events',json=conflict);self.assertNotEqual(duplicate.status_code,200);self.assertEqual(duplicate.json()['reason'],'ORDER_ALREADY_EXISTS')
    _,a=event(dict(event_id='fill',kind='FILL',order_id='broker1',quantity=2,price='90',fees='2',executed_at='2026-11-06T15:00:00Z'));self.assertFalse(a['cash_confirmation_valid']);self.assertEqual(a['orders'][0]['remaining_quantity'],2)
    _,a=event(dict(event_id='cash2',kind='CASH_CONFIRM',amount='618',cash_basis='AVAILABLE_AFTER_RESERVATIONS'));self.assertEqual((a['available_cash'],a['total_uninvested_cash']),('618','818'))
    body,a=event(dict(event_id='cancel',kind='CANCEL',order_id='broker1'));self.assertEqual((a['available_cash'],a['reserved_cash'],a['total_uninvested_cash']),('818','0','818'))
    self.assertEqual(c.post('/api/strategy-account/events',json=body).json()['account']['revision'],a['revision']);self.assertEqual(len(a['holdings']),1);self.assertEqual(a['holdings'][0]['quantity'],2)
if __name__=='__main__':unittest.main()

