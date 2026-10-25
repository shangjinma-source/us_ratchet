from copy import deepcopy
from datetime import timedelta
from functools import partial
from hashlib import sha256
from fractions import Fraction
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import json
import unittest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from core.strategy_account_ledger import canonical
from core.strategy_account_store import StrategyAccountStore
from api.strategy_daily_preview import create_router
from data.strategy_daily_live_adapter import StrategyDailyLiveAdapter
from data.strategy_account_target_inputs import build_target_inputs
from data.strategy_account_execution_limits import build_execution_limits
from data.current_quantity_v2_pullback_runtime import LazyPullbackCapStore
import test_strategy_account_evidence_provider as fixtures

class ReadyHttpTests(unittest.TestCase):
 def test_real_provider_sell_seven_no_cap_no_account_or_target_write(self):
  with TemporaryDirectory() as directory:
   helper=fixtures.ProviderTests();provider,original,clock,_=helper.fixture(directory)
   account=StrategyAccountStore(Path(directory)/'real.sqlite3',clock=lambda:clock[0]);account.initialize('real-strategy',operation_id='init')
   identity=dict(ticker='BBB',security_id='B',source_references=['identity-only'],source_hashes={'identity-only':sha256(b'id').hexdigest()})
   account.append(dict(event_id='fill14',kind='DIRECT_FILL',security_id='B',side='BUY',quantity=14,price='10',fees='0',executed_at='2026-10-30T19:00:00Z',identity_evidence=identity),expected_revision=account.read()['revision'])
   account.append(dict(event_id='cash0',kind='CASH_CONFIRM',amount='0',cash_basis='TOTAL_UNINVESTED'),expected_revision=account.read()['revision'])
   state=account.read();evidence=provider.selection(state)
   inputs=build_target_inputs(state=state,now=clock[0].isoformat(),maximum_mark_age_seconds=900,**evidence)
   payload=dict(input_binding=inputs['binding'],input_id=inputs['input_id'],target_quantities={'B':21})
   target=dict(target_id='b'*64,payload=dict(account_id=state['account_id'],target_month='2026-11',target_quantities={'B':21},decision=dict(status='TARGET_READY',payload=payload,decision_id=sha256(canonical(payload)).hexdigest())))
   cap_path=Path(directory)/'caps.sqlite3'
   caps=LazyPullbackCapStore(cap_path,clock=lambda:clock[0].isoformat(),max_history_rows=32,max_history_bytes=1024*1024)
   provider.limits=partial(build_execution_limits,cap_store=caps)
   monthly=SimpleNamespace(accounts=account,current=lambda:deepcopy(target),validate_current_target_pins=lambda:None,selection=SimpleNamespace(fees='10'))
   def reader(state,target,now):
    return dict(status='VERIFIED',signal=dict(account_id=state['account_id'],account_revision=state['revision'],target_id=target['target_id'],policy_id='test-only',evidence_id='fixture-reviewed',observed_at=(now-timedelta(days=1)).isoformat(),available_at=(now-timedelta(hours=1)).isoformat(),valid_from=(now-timedelta(minutes=30)).isoformat(),valid_until=(now+timedelta(minutes=30)).isoformat(),effective_target_quantities={'B':7}))
   service=StrategyDailyLiveAdapter(monthly_service=monthly,evidence_reader=reader,clock=lambda:clock[0],enabled=True,policy_id='test-only',execution_provider=provider.execution)
   app=FastAPI();app.include_router(create_router(service=service));before=account.path.read_bytes();base=deepcopy(target)
   with TestClient(app) as client:response=client.post('/api/strategy-daily/preview',json=dict(expected_revision=state['revision'],target_id=target['target_id']))
   self.assertEqual(response.status_code,200,response.text);result=response.json()
   self.assertEqual(result['status'],'CONDITIONAL_PREVIEW_READY');order=result['new_orders'][0]
   self.assertEqual((order['side'],order['quantity']),('SELL',7));self.assertEqual(Fraction(order['estimated_cash_change']),Fraction(70)*Fraction(999,1000))
   self.assertFalse(result['reference_quotes']['B']['buy_evaluated']);self.assertFalse(cap_path.exists())
   self.assertEqual(account.path.read_bytes(),before);self.assertEqual(target,base)
   binding=result['execution_binding'];raw=Path(binding['path']).read_bytes();self.assertEqual(sha256(raw).hexdigest(),binding['sha256'])
   lineage=json.loads(raw);self.assertEqual(lineage['effective_target_quantities'],{'B':7});self.assertEqual(lineage['base_decision_id'],base['payload']['decision']['decision_id'])
   receipts=list(Path(binding['path']).parent.glob('*/complete.json'));self.assertEqual(len(receipts),1)
   self.assertEqual(json.loads(receipts[0].read_bytes())['source_hashes'][binding['path']],binding['sha256'])
