"""Real registration/publication/adoption/finish chain; synthetic data and process.
Full V34 service construction is replaced; production deployment has separate evidence.
"""
import json
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import test_roa_monthly_registration as registration_fixture
from scripts.research.prepare_roa_monthly_registration import prepare
from scripts.research.prepare_roa_monthly_publication import prepare_publication
from scripts.research.advance_roa_monthly_release import advance
from core.strategy_account_store import StrategyAccountStore


class IntegratedAdoptionTests(unittest.TestCase):
 def setUp(self):
  self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
  args,save,_,_=registration_fixture.RegistrationTests().fixture(self.root)
  registration=prepare(**args)
  active=dict(path=args['active_path'],sha256=args['active_sha256'])
  for module in ('scripts.research.prepare_roa_monthly_publication','scripts.research.adopt_roa_monthly_registration'):
   patched=patch(module+'.build_unified_server_preparation_v34',return_value={'validate_code':lambda:None})
   patched.start();self.addCleanup(patched.stop)
  prepare_publication(root=self.root,active=active,registration=registration,output_directory='preflight')
  ref=dict(path='preflight/validated.json',sha256=sha256((self.root/'preflight/validated.json').read_bytes()).hexdigest())
  self.request=dict(active=active,registration=registration,publication=ref,month='2026-12',epoch='epoch',expected_process={'pid':1})
  self.store=StrategyAccountStore(self.root/'data/strategy_account/real_strategy.sqlite3')
  self.store.initialize('isolated-test',operation_id='initialize')
  self.before=self.store.read();self.restarts=0;self.change_account=False
  self.loaded=active['sha256'];self.month='2026-11'
 def restart(self,**kw):
  self.restarts+=1;self.loaded=sha256((self.root/'active.json').read_bytes()).hexdigest();self.month='2026-12'
  if self.change_account:
   self.store.append(dict(event_id='concurrent-cash',kind='CASH_CONFIRM',amount='123',cash_basis='TOTAL_UNINVESTED'),expected_revision=self.store.read()['revision'])
 def adapter(self,*a,**kw):
  return SimpleNamespace(inspect=lambda:dict(healthy=True,active_sha256=self.loaded,month=self.month,epoch='epoch',process_identity={'pid':1}),
                         get_json=lambda _:self.store.read(),restart=self.restart)
 def run_it(self):
  return advance(root=self.root,request=self.request,output_directory='tmp/attempt',execute=True,adapter_factory=self.adapter)
 def test_real_receipts_and_sqlite_survive_reentry(self):
  result=self.run_it();self.run_it()
  self.assertEqual(result['status'],'MONTH_ADOPTED_RUNTIME_VERIFIED_NEXT_TASK_PENDING')
  self.assertEqual(self.restarts,1)
  self.assertEqual(self.store.read(),self.before)
  success=json.loads((self.root/'tmp/attempt/runtime/success.json').read_bytes())
  adopted=json.loads((self.root/'tmp/attempt/adoption/adoption.json').read_bytes())
  self.assertEqual(success['scope']['active_sha256'],adopted['active_sha256'])
  self.assertEqual((self.root/'tmp/attempt/adoption/rollback_active.json').read_bytes(),(self.root/'release/rollback_active.json').read_bytes())
 def test_concurrent_cash_not_erased_or_reported_success(self):
  self.change_account=True
  with self.assertRaisesRegex(ValueError,'ACCOUNT_OR_LEDGER_CHANGED'):self.run_it()
  self.assertFalse((self.root/'tmp/attempt/runtime/success.json').exists())
  self.assertNotEqual(self.store.read(),self.before)
  with self.assertRaisesRegex(ValueError,'ACCOUNT_OR_LEDGER_CHANGED'):self.run_it()
  self.assertEqual(self.restarts,1)

if __name__=='__main__':unittest.main()

