from pathlib import Path
from tempfile import TemporaryDirectory
from datetime import datetime,timezone
import unittest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.strategy_account import create_router

class APITests(unittest.TestCase):
 def test_valuation_without_confirmed_cash_is_readonly_and_revision_bound(self):
  from api.strategy_account import StrategyAccountService
  with TemporaryDirectory() as d:
   now=datetime(2026,10,16,15,tzinfo=timezone.utc)
   mark=dict(security_id='A',ticker='AAA',currency='USD',price='12',observed_at=now.isoformat())
   service=StrategyAccountService(database_path=Path(d)/'a.db',account_id='a',resolver=lambda t:dict(ticker=t,security_id='A',source_references=['id'],source_hashes={'id':'a'*64}),clock=lambda:now,valuation_provider=lambda state:{'A':mark})
   account=service.initialize({'event_id':'init'})['account']
   def event(value):
    nonlocal account
    account=service.append(dict(expected_revision=account['revision'],event=value))['account']
   event(dict(event_id='cash',kind='CASH_CONFIRM',amount='100',cash_basis='TOTAL_UNINVESTED'))
   event(dict(event_id='fill',kind='DIRECT_FILL',ticker='AAA',side='BUY',quantity=2,price='10',fees='0',executed_at='2026-10-16T14:00:00Z'))
   self.assertEqual(account['cash_summary']['derived_total_uninvested_cash_estimate'],'80')
   before=service.store.path.read_bytes();result=service.valuation()
   self.assertEqual(result['market_value'],'24');self.assertIsNone(result['strategy_total'])
   self.assertFalse(result['cash_confirmed']);self.assertEqual(service.store.path.read_bytes(),before)
   app=FastAPI();app.include_router(create_router(database_path=service.store.path,account_id='a',resolver=service.resolver,clock=lambda:now,valuation_provider=lambda state:{'A':mark}))
   with TestClient(app) as client:
    response=client.get('/api/strategy-account/valuation')
    self.assertEqual(response.status_code,200,response.text)
    self.assertEqual(response.json()['account_revision'],account['revision'])
    self.assertIsNone(response.json()['strategy_total'])
    self.assertEqual(client.get('/api/strategy-account/valuation?cash=100').status_code,422)
   self.assertEqual(service.store.path.read_bytes(),before)
   event(dict(event_id='reconfirm',kind='CASH_CONFIRM',amount='80',cash_basis='TOTAL_UNINVESTED'))
   self.assertEqual(service.valuation()['strategy_total'],'104')
   def changing(state):
    event(dict(event_id='race',kind='CASH_CONFIRM',amount='81',cash_basis='TOTAL_UNINVESTED'))
    return {'A':mark}
   service.valuation_provider=changing
   with self.assertRaisesRegex(ValueError,'STALE_REVISION'):service.valuation()
 def test_readonly_fill_cost_and_manual_cash_summary(self):
  from api.strategy_account import StrategyAccountService
  with TemporaryDirectory() as d:
   service=StrategyAccountService(database_path=Path(d)/'a.db',account_id='a',resolver=lambda t:dict(ticker=t,security_id='A',source_references=['id'],source_hashes={'id':'a'*64}),clock=lambda:datetime(2026,10,16,15,tzinfo=timezone.utc))
   account=service.initialize({'event_id':'init'})['account']
   def event(value):
    nonlocal account
    account=service.append(dict(expected_revision=account['revision'],event=value))['account']
   event(dict(event_id='cash',kind='CASH_CONFIRM',amount='1000',cash_basis='TOTAL_UNINVESTED'))
   event(dict(event_id='open',kind='ORDER_OPEN',order_id='o',ticker='AAA',side='BUY',quantity=4,limit_price='10',fee_per_share='1'))
   self.assertEqual(account['fills'],[])
   event(dict(event_id='fill',kind='FILL',order_id='o',quantity=4,price='10',fees='4',executed_at='2026-10-16T14:00:00Z'))
   self.assertEqual(account['cash'],'1000');self.assertFalse(account['cash_confirmation_valid'])
   self.assertEqual(account['holding_costs'][0]['average_cost'],'11')
   self.assertEqual(account['fills'][0]['fill_id'],'fill');self.assertEqual(account['fills'][0]['ticker'],'AAA')
   self.assertEqual(account['cash_summary']['recorded_fill_cash_delta_since_confirmation'],'-44')
   event(dict(event_id='sell',kind='DIRECT_FILL',ticker='AAA',side='SELL',quantity=1,price='15',fees='1',executed_at='2026-10-16T14:10:00Z'))
   self.assertEqual(account['holding_costs'][0]['total_cost'],'33')
   self.assertEqual(account['cash_summary']['recorded_fill_cash_delta_since_confirmation'],'-30')
   before=service.store.path.read_bytes();self.assertEqual(service.read()['account'],account)
   self.assertEqual(service.store.path.read_bytes(),before)
   event(dict(event_id='reconfirm',kind='CASH_CONFIRM',amount='970',cash_basis='TOTAL_UNINVESTED'))
   self.assertEqual(account['cash_summary']['recorded_fill_cash_delta_since_confirmation'],'0')
   self.assertTrue(account['cash_summary']['current_balance_confirmed'])
   self.assertEqual(len(account['fills']),2)
 def test_http_lifecycle_strict_scope_retry_and_times(self):
  with TemporaryDirectory() as d:
   path=Path(d)/'missing'/'strategy.db';calls=[]
   def resolver(ticker):
    calls.append(ticker)
    return dict(ticker=ticker,security_id='SID-A',source_references=['identity.json'],source_hashes={'identity.json':'a'*64})
   app=FastAPI();app.include_router(create_router(database_path=path,account_id='fixed',resolver=resolver,clock=lambda:datetime(2026,10,16,15,tzinfo=timezone.utc)))
   with TestClient(app) as client:
    base='/api/strategy-account'
    self.assertEqual(client.get(base).json()['status'],'NOT_INITIALIZED');self.assertFalse(path.parent.exists())
    self.assertEqual(client.post(base+'/initialize',json={'event_id':'init','account_id':'evil'}).status_code,422)
    ready=client.post(base+'/initialize',json={'event_id':'init'}).json()
    self.assertEqual(client.post(base+'/initialize',json={'event_id':'init'}).json(),ready)
    self.assertEqual(client.post(base+'/initialize',json={'event_id':'other'}).status_code,409)
    def submit(event,revision):return client.post(base+'/events',json={'expected_revision':revision,'event':event})
    cash=dict(event_id='cash',kind='CASH_CONFIRM',amount='100',cash_basis='TOTAL_UNINVESTED')
    confirmed=submit(cash,ready['account']['revision']).json()
    fill=dict(event_id='fill',kind='DIRECT_FILL',ticker='AAA',side='BUY',quantity=2,price='10',fees='1',executed_at='2026-10-16T14:00:00Z')
    filled=submit(fill,confirmed['account']['revision']).json()
    self.assertEqual(filled['account']['holdings'],[dict(security_id='SID-A',ticker='AAA',quantity=2)])
    self.assertFalse(filled['account']['cash_confirmation_valid']);self.assertEqual(filled['account']['cash'],'100')
    self.assertEqual(submit(fill,confirmed['account']['revision']).json(),filled);self.assertEqual(calls,['AAA'])
    self.assertNotIn('events',filled['account'])
    future=dict(fill,event_id='future',executed_at='2026-10-16T16:00:00Z')
    self.assertEqual(submit(future,filled['account']['revision']).json()['reason'],'FUTURE_EXECUTED_AT')
    self.assertEqual(submit(dict(fill,security_id='evil'),filled['account']['revision']).status_code,422)
    self.assertEqual(client.post(base+'/initialize',content=' '*9000).json()['reason'],'BODY_TOO_LARGE')
    self.assertEqual(client.post(base+'/initialize',content='{"event_id":"a","event_id":"b"}').json()['reason'],'DUPLICATE_JSON_FIELD')
    self.assertEqual(client.get(base+'?path=evil').status_code,422)
    self.assertEqual(client.get(base).json()['account'],filled['account'])
 def test_pending_fill_time_and_cancel_are_preserved(self):
  from api.strategy_account import StrategyAccountService
  with TemporaryDirectory() as d:
   service=StrategyAccountService(database_path=Path(d)/'a.db',account_id='a',resolver=lambda t:dict(ticker=t,security_id='A',source_references=['id'],source_hashes={'id':'a'*64}),clock=lambda:datetime(2026,10,16,15,tzinfo=timezone.utc))
   initial=service.initialize({'event_id':'init'})
   state,_=service.store.append(dict(event_id='cash',kind='CASH_CONFIRM',amount='100',cash_basis='TOTAL_UNINVESTED'),expected_revision=initial['account']['revision'])
   opened=service.append(dict(event=dict(event_id='open',kind='ORDER_OPEN',order_id='one',ticker='AAA',side='BUY',quantity=4,limit_price='10',fee_per_share='0'),expected_revision=state['revision']))
   state=service.store.read()
   self.assertEqual(opened['account']['orders'][0]['ticker'],'AAA')
   fill=dict(event_id='fill',kind='FILL',order_id='one',quantity=1,price='10',fees='0',executed_at='2026-10-16T14:00:00Z')
   result=service.append(dict(expected_revision=state['revision'],event=fill))
   self.assertEqual(result['effect']['executed_at'],fill['executed_at']);self.assertEqual(result['account']['orders'][0]['remaining_quantity'],3)
   result=service.append(dict(expected_revision=result['account']['revision'],event=dict(event_id='cancel',kind='CANCEL',order_id='one')))
   self.assertEqual(result['account']['orders'],[])
   self.assertEqual(service.store.read()['events'][-2]['payload']['executed_at'],fill['executed_at'])

if __name__=='__main__':unittest.main()
