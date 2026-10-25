from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from core.strategy_account_ledger import canonical
from data.strategy_daily_domain_runner_v1 import run_domain_sources,RUNNER_SOURCES
import test_strategy_daily_first_window_v1 as fixtures

class DomainRunnerTests(unittest.TestCase):
 def setup(self,folder,cancel=True,multiple=False):
  c,config,captured=fixtures.FirstWindowTests().case(folder);root=Path(folder)
  if cancel:
   c.store.append(dict(event_id='cancel-a',kind='CANCEL',order_id='a-pending'),expected_revision=c.store.read()['revision'])
   c.state=c.store.read()
  if multiple:
   from data.strategy_account_identity import PinnedStrategyIdentity
   from data.strategy_continuous32_target_decision import decide_target,REQUIRED_PINS
   from data.strategy_daily_security_domain_v1 import locate_unit_baseline_sources
   resolver=PinnedStrategyIdentity(root,config['identity']['path'],config['identity']['sha256'])
   c.store.append(dict(event_id='held-a',kind='DIRECT_FILL',security_id='A',side='BUY',
    quantity=1,price='100',fees='0',executed_at='2026-10-30T19:00:00Z',identity_evidence=resolver('AAA')),
    expected_revision=c.store.read()['revision'])
   c.store.append(dict(event_id='after-held-a',kind='CASH_CONFIRM',amount='100',cash_basis='TOTAL_UNINVESTED'),
    expected_revision=c.store.read()['revision'])
   c.state=c.store.read();args=c.provider.selection(c.state)
   for name in REQUIRED_PINS:
    body=(fixtures.ROOT/name).read_bytes();args['source_package']['files'][name]=body
    args['source_package']['source_hashes'][name]=sha256(body).hexdigest()
   decision=decide_target(state=c.state,now=c.clock[0].isoformat(),maximum_mark_age_seconds=900,**args)
   c.target['payload'].update(decision=decision,target_quantities=decision['payload']['target_quantities'])
   c.target['target_id']=sha256(canonical(c.target['payload'])).hexdigest()
   config['unit_source_paths']=locate_unit_baseline_sources(root=root,evidence_root='capture',
    binding=decision['payload']['input_binding'])
  pins=[]
  for name in RUNNER_SOURCES:
   raw=(fixtures.ROOT/name).read_bytes();path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
   pins.append(dict(path=name,sha256=sha256(raw).hexdigest()))
  cfg=dict(schema='SERVER_DAILY_DOMAIN_RUNNER_V1',source_pins=pins,calendar=config['calendar'],
   identity=config['identity'],unit_source_paths=config['unit_source_paths'],
   first_execution_date='2026-11-02',runs_root='domain-runs')
  def run(execute=True,broken=False):
   raw=canonical(cfg)
   def daily(ticker,*args):
    document=json.loads(captured['daily.response.bin']);document['chart']['result'][0]['meta']['symbol']=ticker
    return dict(status=500 if broken else 200,body=canonical(document))
   return run_domain_sources(root=root,configuration_bytes=raw,configuration_sha256=sha256(raw).hexdigest(),
    account_reader=c.store.read,target_reader=lambda:c.target,execute=execute,
    clock=lambda:c.clock[0],fetch_daily=daily,
    fetch_official=lambda:dict(status=200,body=captured['official.response.bin']))
  return c,run,root
 def test_actual_saved_capture_review_aggregate_once(self):
  with TemporaryDirectory() as folder:
   c,run,root=self.setup(folder);before=c.store.path.read_bytes()
   self.assertEqual(run(False)['status'],'DRY_RUN_NO_HTTP_NO_FILES')
   self.assertFalse((root/'domain-runs').exists())
   result=run();self.assertEqual(result['status'],'CONDITIONAL_DOMAIN_PACKET_SAVED_POLICY_UNRELEASED',result)
   self.assertEqual(result['http_calls'],2)
   receipt=json.loads((root/'domain-runs/2026-11-02/receipt.json').read_bytes())
   self.assertIsNone(receipt['release_sha256']);self.assertEqual(len(receipt['aggregate_parents']),1)
   self.assertEqual(run()['status'],'EXISTING_DOMAIN_PACKET_VERIFIED')
   self.assertEqual(c.store.path.read_bytes(),before)
 def test_two_securities_keep_individual_reviews_then_aggregate(self):
  with TemporaryDirectory() as folder:
   c,run,root=self.setup(folder,multiple=True);before=c.store.path.read_bytes()
   result=run();self.assertEqual(result['status'],'CONDITIONAL_DOMAIN_PACKET_SAVED_POLICY_UNRELEASED',result)
   self.assertEqual(result['http_calls'],4)
   receipt=json.loads((root/'domain-runs/2026-11-02/receipt.json').read_bytes())
   self.assertEqual({p['security_id'] for p in receipt['aggregate_parents']},{'A','B'})
   self.assertEqual(c.store.path.read_bytes(),before)
 def test_missing_domain_wait_and_failure_never_retried(self):
  with TemporaryDirectory() as folder:
   c,run,root=self.setup(folder,False)
   self.assertEqual(run()['status'],'WAIT_UNIT_BASELINE');self.assertFalse((root/'domain-runs').exists())
  with TemporaryDirectory() as folder:
   c,run,root=self.setup(folder)
   result=run(broken=True);self.assertEqual(result['status'],'NEEDS_RECOVERY',result)
   self.assertEqual(result['http_calls'],2)
   self.assertEqual(run()['status'],'NEEDS_RECOVERY')
   self.assertFalse((root/'domain-runs/2026-11-02/receipt.json').exists())
 def test_saved_packet_tamper_and_old_month_are_not_recaptured(self):
  with TemporaryDirectory() as folder:
   c,run,root=self.setup(folder)
   c.target['payload']['target_month']='2026-10'
   self.assertEqual(run()['status'],'WAIT_MONTHLY_TARGET')
   self.assertFalse((root/'domain-runs').exists())
  with TemporaryDirectory() as folder:
   c,run,root=self.setup(folder);self.assertEqual(run()['http_calls'],2)
   terminal_path=root/'domain-runs/2026-11-02/terminal.json'
   terminal=json.loads(terminal_path.read_bytes());terminal['finished_at']='2099-01-01T00:00:00Z'
   terminal_path.write_bytes(canonical(terminal))
   with self.assertRaisesRegex(ValueError,'DOMAIN_SAVED_TIME'):run()

if __name__=='__main__':unittest.main()
