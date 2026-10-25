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

class MixedPreviewTests(unittest.TestCase):
 def test_zero_cash_sell_old_buy_new_waits_with_real_provider(self):
  with TemporaryDirectory() as directory:
   helper=fixtures.ProviderTests();provider,original,clock,_=helper.fixture(directory)
   account=StrategyAccountStore(Path(directory)/'real.sqlite3',clock=lambda:clock[0]);account.initialize('real-strategy',operation_id='init')
   identity=dict(ticker='AAA',security_id='A',source_references=['identity-only'],source_hashes={'identity-only':sha256(b'id').hexdigest()})
   account.append(dict(event_id='fill14',kind='DIRECT_FILL',security_id='A',side='BUY',quantity=14,price='10',fees='0',executed_at='2026-10-30T19:00:00Z',identity_evidence=identity),expected_revision=account.read()['revision'])
   account.append(dict(event_id='cash0',kind='CASH_CONFIRM',amount='0',cash_basis='TOTAL_UNINVESTED'),expected_revision=account.read()['revision'])
   state=account.read();evidence=provider.selection(state)
   inputs=build_target_inputs(state=state,now=clock[0].isoformat(),maximum_mark_age_seconds=900,**evidence)
   payload=dict(input_binding=inputs['binding'],input_id=inputs['input_id'],target_quantities={'B':5})
   target=dict(target_id='b'*64,payload=dict(account_id=state['account_id'],target_month='2026-11',target_quantities={'B':5},decision=dict(status='TARGET_READY',payload=payload,decision_id=sha256(canonical(payload)).hexdigest())))
   cap_path=Path(directory)/'caps.sqlite3'
   caps=LazyPullbackCapStore(cap_path,clock=lambda:clock[0].isoformat(),max_history_rows=32,max_history_bytes=1024*1024)
   provider.limits=partial(build_execution_limits,cap_store=caps)
   from data.strategy_daily_mixed_preview import preview_zero_cash_mixed
   now=clock[0]
   signal=dict(account_id=state['account_id'],account_revision=state['revision'],target_id=target['target_id'],policy_id='test-only',evidence_id='fixture-reviewed',observed_at=(now-timedelta(days=1)).isoformat(),available_at=(now-timedelta(hours=1)).isoformat(),valid_from=(now-timedelta(minutes=30)).isoformat(),valid_until=(now+timedelta(minutes=30)).isoformat(),effective_target_quantities={'A':0,'B':5})
   target_before=deepcopy(target);signal_before=deepcopy(signal);db_before=account.path.read_bytes()
   result=preview_zero_cash_mixed(account_store=account,target_store=SimpleNamespace(current=lambda:deepcopy(target)),signal_verifier=lambda *args:signal,execution_provider=provider.execution,validate_sources=lambda:None,policy_id='test-only',clock=lambda:clock[0],fee_bps='10')
   self.assertEqual(result['status'],'CONDITIONAL_SELL_PREVIEW_BUYS_WAIT')
   self.assertEqual([(o['security_id'],o['side'],o['quantity']) for o in result['new_orders']],[('A','SELL',14)])
   self.assertEqual(result['waiting_cash'],[dict(security_id='B',quantity=5,reason='WAIT_CASH_NO_SELL_PROCEEDS_ASSUMED')])
   self.assertEqual(result['effective_target_quantities'],{'A':0,'B':5})
   self.assertEqual(result['execution_quantities'],{'A':0,'B':0})
   self.assertEqual(Fraction(result['difference']['new_buy_cash_required']),0)
   self.assertFalse(cap_path.exists());self.assertEqual(set(result['reference_quotes']),{'A'})
   self.assertFalse(result['reference_quotes']['A']['buy_evaluated'])
   self.assertEqual(target,target_before);self.assertEqual(signal,signal_before);self.assertEqual(account.path.read_bytes(),db_before)
   binding=result['execution_binding'];raw=Path(binding['path']).read_bytes();self.assertEqual(sha256(raw).hexdigest(),binding['sha256'])
   lineage=json.loads(raw);self.assertEqual(lineage['signal'],signal);self.assertEqual(lineage['effective_target_quantities'],{'A':0,'B':5});self.assertEqual(lineage['execution_quantities'],{'A':0,'B':0})
   self.assertEqual(lineage['waiting_buys'],{'B':5})
   self.assertEqual(lineage['base_decision_id'],target['payload']['decision']['decision_id'])
   receipts=list(Path(binding['path']).parent.glob('*/complete.json'));self.assertEqual(len(receipts),1)
   self.assertEqual(json.loads(receipts[0].read_bytes())['source_hashes'][binding['path']],binding['sha256'])
