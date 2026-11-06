from datetime import datetime,timezone
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.strategy_account import StrategyAccountService
from api.roa_strategy import create_router
from data.roa_strategy_service import RoaStrategyService
from data.roa_execution_lifecycle import RoaExecutionLifecycle
from data.roa_cash_flow.composition import attach_flow

class ReadyTests(unittest.TestCase):
 def test_ready_deposit_withdrawal_partial_fill(self):
  with TemporaryDirectory() as d:
   root=Path(d);directory=root/'data/strategy_account';directory.mkdir(parents=True);now=[datetime(2026,11,6,14,31,tzinfo=timezone.utc)]
   identity=dict(ticker='TEST',security_id='sid',source_references=['fixture'],source_hashes={'fixture':'a'*64})
   def marks(state):return {s:dict(security_id=s,ticker='TEST',currency='USD',price='10',observed_at=now[0].isoformat()) for s,q in state['shares'].items() if q}
   account=StrategyAccountService(database_path=directory/'account.sqlite',account_id='test',resolver=lambda _:identity,clock=lambda:now[0],valuation_provider=marks)
   account.initialize({'event_id':'init'})
   account.append(dict(expected_revision=account.store.read()['revision'],event=dict(event_id='start',kind='CASH_CONFIRM',amount='1000',cash_basis='TOTAL_UNINVESTED')))
   old=account.store.read();value=account.valuation();baseline=dict(initial_equity='1000',cash='1000',effective_at=value['valued_at'],account_revision=old['revision'],holdings=[],valuation_evidence=value)
   def pin(name,obj):
    p=directory/name;raw=json.dumps(obj).encode();p.write_bytes(raw);return dict(path=p.relative_to(root).as_posix(),sha256=sha256(raw).hexdigest())
   config=dict(schema='ROA_FLOW_CLASSIFICATION_CONFIG_V1',baseline=pin('baseline.json',baseline),ledger=pin('ledger.json',old),sidecar_path='data/strategy_account/flow.sqlite')
   lifecycle=RoaExecutionLifecycle(path=directory/'life.json',account_id='test',strategy_epoch='epoch',contract_sha256='a'*64)
   def calendar(day):return dict(open_at=day+'T14:30:00Z',close_at=day+'T21:00:00Z')
   def quotes(state,sids,session,phase,at):
    return dict(marks={s:dict(security_id=s,price='10',price_basis='current',currency='USD',observed_at=at.isoformat()) for s in sids},limits={s:dict(security_id=s,buy='10',sell='10',price_basis='current',observed_at=at.isoformat()) for s in sids},opening_prices={s:'10' for s in sids},opening_session=session,quote_valid_until='2026-11-06T14:34:00Z')
   signal=dict(signal_id='synthetic',decision_date='2026-10-30',signal_date='2026-11-05',execution_not_before_session='2026-11-06',risk_on=True,weights={'sid':'1/10'},securities=[identity],source_hashes={})
   roa=RoaStrategyService(account_service=account,lifecycle=lifecycle,signal_provider=lambda:signal,session_provider=calendar,quote_provider=quotes,clock=lambda:now[0],execution_admission=dict(enabled=True,strategy_epoch='epoch',contract_sha256='a'*64,open_window_seconds=300,close_window_seconds=300))
   prepared=attach_flow(prepared=dict(roa_service=roa,router=create_router(coordinator=roa)),root=root,configuration=config,clock=lambda:now[0],validate_sources=lambda:None);addon=prepared['cash_classification'];addon.store.initialize();app=FastAPI();app.include_router(prepared['router'])
   with TestClient(app) as client:
    def cash(event,amount):
     result=client.post('/api/strategy-roa/cash-save-and-preview',json=dict(expected_revision=account.store.read()['revision'],event=dict(event_id=event,kind='CASH_CONFIRM',amount=amount,cash_basis='TOTAL_UNINVESTED')))
     self.assertEqual(result.status_code,200);self.assertTrue(result.json()['cash_saved']);self.assertEqual(result.json()['status'],'READY',result.text);return result.json()
    now[0]=datetime(2026,11,6,14,31,10,tzinfo=timezone.utc)
    result=cash('deposit','1100');target=result['target_quantities']['sid'];self.assertGreater(target,4)
    result=cash('withdraw','1000');self.assertEqual(result['target_quantities']['sid'],target)
    audit=client.get('/api/strategy-account/cash-classification').json()
    for row in audit['unresolved']:
     kind='DEPOSIT' if row['unexplained_net_change']=='100' else 'WITHDRAWAL'
     doc=dict(schema='CASH_CHANGE_CLASSIFICATION_V1',account_id='test',cash_event_id=row['event_id'],before_revision=row['before_revision'],after_revision=row['after_revision'],net_change=row['unexplained_net_change'],items=[dict(item_id='one',kind=kind,amount=row['unexplained_net_change'],effective_at='2026-11-06T14:31:05Z')])
     self.assertEqual(client.post('/api/strategy-account/cash-classification',json=dict(expected_revision=account.store.read()['revision'],document=doc)).status_code,200)
    before=account.store.read();self.assertEqual(client.get('/api/strategy-account/cash-classification/profit').json()['profit']['profit_amount'],'0');self.assertEqual(account.store.read(),before)
    account.append(dict(expected_revision=before['revision'],event=dict(event_id='partial',kind='DIRECT_FILL',ticker='TEST',side='BUY',quantity=4,price='10',fees='0',executed_at='2026-11-06T14:31:10Z')))
    now[0]=datetime(2026,11,6,14,31,20,tzinfo=timezone.utc)
    result=cash('afterfill','960');self.assertEqual(result['rows'][0]['held'],4);self.assertEqual(result['rows'][0]['quantity'],target-4)
    final=client.get('/api/strategy-account/cash-classification/profit').json();self.assertEqual(final['unresolved'],[]);self.assertEqual(final['profit']['profit_amount'],'0')
    account.append(dict(expected_revision=account.store.read()['revision'],event=dict(event_id='sell',kind='DIRECT_FILL',ticker='TEST',side='SELL',quantity=2,price='10',fees='1',executed_at='2026-11-06T14:31:20Z')))
    now[0]=datetime(2026,11,6,14,31,30,tzinfo=timezone.utc)
    cash('after_sell','979');last=client.get('/api/strategy-account/cash-classification/profit').json();self.assertEqual(last['unresolved'],[]);self.assertEqual(last['profit']['profit_amount'],'-1')
if __name__=='__main__':unittest.main()
