from pathlib import Path
from tempfile import TemporaryDirectory
from hashlib import sha256
import unittest
from unittest.mock import patch
from datetime import timedelta
from core.strategy_account_ledger import canonical
from data.strategy_account_runtime import ACCOUNT_ID
from data.strategy_continuous32_runtime import RUNTIME_PATHS
from data.strategy_profiled_runtime import build_runtime
from data.strategy_profiled_runtime_archive import configuration_for_target
from data.strategy_continuous32_target_decision import PROFILE_ID
from data.strategy_account_identity import PinnedStrategyIdentity
from data.strategy_account_market_capture import StrategyAccountMarketCapture
import test_strategy_account_evidence_provider as fixtures

class UpgradeTransportTests(unittest.TestCase):
 def test_explicit_v3_full_preflight_and_current_package_materialization(self):
  with TemporaryDirectory() as temp:
   original,_,now,root=fixtures.ProviderTests().fixture(temp)
   from data.strategy_upgrade_action_transport_v3 import SOURCES,materialize_transport_configuration,PinnedUpgradeActionTransportV3
   from data.strategy_account_action_capture_v3 import StrategyAccountActionCaptureV3
   for name in SOURCES:
    destination=root/name;destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes((Path(__file__).resolve().parents[1]/name).read_bytes())
   reference=materialize_transport_configuration(root=root,relative_path='transport.json',authorized=True)
   transport=PinnedUpgradeActionTransportV3(root=root,configuration_path=reference['path'],configuration_sha256=reference['sha256'])
   def put(name,value):
    raw=canonical(value);path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw);return sha256(raw).hexdigest()
   pins={}
   for name in RUNTIME_PATHS:
    raw=(Path(__file__).resolve().parents[1]/name).read_bytes();dest=root/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw);pins[name]=sha256(raw).hexdigest()
   (root/'identity-proof').write_bytes(b'identity')
   identity=dict(candidates=[dict(ticker=t,security_id=s,issuer_id=s,status='READY_CONDITIONAL',identity_reviewed=True,identity_source_references=['identity-proof']) for t,s in [('AAA','A'),('BBB','B')]],source_hashes={'identity-proof':sha256(b'identity').hexdigest()})
   config=dict(schema='REAL_STRATEGY_CONTINUOUS32_RUNTIME_V1',selector_profile=PROFILE_ID,target_month='2026-11',training_manifest=original.manifest_path,training_sha256=original.manifest_hash,training_closed_at=original.closed,identity_manifest='capital-identity.json',identity_sha256=put('capital-identity.json',identity),runtime_pins=pins)
   archive=dict(schema='PROFILED_STRATEGY_RUNTIME_ARCHIVE_V1',entries=[dict(configuration_path='runtime.json',configuration_sha256=put('runtime.json',config))])
   snapshot=dict(registry_path='unused-registry.json',registry_sha256='0'*64,archive_path='archive.json',archive_sha256=put('archive.json',archive))
   calls=[]
   def builder(**kwargs):
    runtime=transport.build_runtime(**kwargs);provider=runtime.execution_provider.__self__
    self.assertIsInstance(provider.actions,StrategyAccountActionCaptureV3)
    def fetch(ticker):
     start=int(now[0].replace(hour=14,minute=30,second=0).timestamp());last=int(now[0].timestamp())
     return canonical(dict(chart=dict(error=None,result=[dict(meta=dict(symbol=ticker,currency='USD',instrumentType='EQUITY',exchangeTimezoneName='America/New_York',dataGranularity='1m',regularMarketPrice=10,regularMarketTime=last,currentTradingPeriod=dict(regular=dict(start=start,end=start+23400))),timestamp=list(range(start,start+1800,60)),indicators=dict(quote=[dict(open=[10]*30,high=[11]*30,low=[9]*30,close=[10]*30,volume=[10]*30)]))])))
    provider.market=StrategyAccountMarketCapture(identity_resolver=PinnedStrategyIdentity(root,config['identity_manifest'],config['identity_sha256']),fetch=fetch,clock=lambda:now[0],max_mark_age=900)
    provider.actions.fetch=original.actions.fetch;provider.actions.rss_fetch=original.actions.rss_fetch;provider.actions.clock=original.actions.clock
    calls.append(runtime);return runtime
   runtime=builder(root=root,configuration=config,clock=lambda:now[0])
   account=runtime.accounts;account.initialize(ACCOUNT_ID,operation_id='init')
   account.append(dict(kind='CASH_CONFIRM',event_id='cash',amount='1000',cash_basis='TOTAL_UNINVESTED'),expected_revision=account.read()['revision'])
   before=account.path.read_bytes()
   target=runtime.generate(event_id='continuous-initial',reason='INITIAL',expected_revision=account.read()['revision'],previous_target_id=None)
   self.assertEqual(target['payload']['decision']['payload']['input_binding']['selector_profile'],PROFILE_ID)
   resolved=configuration_for_target(root=root,archive_path='archive.json',archive_sha256=snapshot['archive_sha256'],target=target)
   self.assertEqual(resolved,config)
   preview=runtime.preview()
   self.assertEqual(preview['status'],'READY')
   self.assertEqual(account.path.read_bytes(),before)
   self.assertEqual(runtime.targets.current(),target)
   # Old configurations remain actual old selector builders, never relabelled.
   old=dict(config,schema='REAL_STRATEGY_RUNTIME_V1');old.pop('selector_profile')
   oldruntime=build_runtime(root=root,configuration=old,clock=lambda:now[0])
   from data.strategy_account_target_service import StrategyAccountTargetService
   self.assertIsInstance(oldruntime.selection,StrategyAccountTargetService)
   oldprovider=oldruntime.execution_provider.__self__
   oldprovider.market=runtime.execution_provider.__self__.market;oldprovider.actions=original.actions
   oldtarget=oldruntime.generate(event_id='old-explicit',reason='EXPLICIT_RECONFIGURE',expected_revision=account.read()['revision'],previous_target_id=target['target_id'])
   archive['entries'].append(dict(configuration_path='old-runtime.json',configuration_sha256=put('old-runtime.json',old)))
   both=put('both-archive.json',archive)
   self.assertEqual(configuration_for_target(root=root,archive_path='both-archive.json',archive_sha256=both,target=oldtarget),old)
   now[0]+=timedelta(seconds=1)
   self.assertEqual(oldruntime.preview()['status'],'READY')
   with self.assertRaisesRegex(ValueError,'CONTINUOUS32_PROFILE_CHANGED'):runtime.preview()
   self.assertEqual(account.path.read_bytes(),before)
   with patch.object(runtime.targets,'current',side_effect=[target,oldtarget]),patch.object(runtime,'execution_provider',side_effect=AssertionError('must not capture')) as capture:
    with self.assertRaisesRegex(ValueError,'TARGET_CHANGED_BEFORE_PREVIEW'):runtime.preview()
    capture.assert_not_called()
   from data.strategy_profiled_rolling_router import ProfiledRollingMonthlyRuntimeRouter
   snap=dict(snapshot,archive_path='both-archive.json',archive_sha256=both,revision=0)
   router=ProfiledRollingMonthlyRuntimeRouter(root=root,initial_snapshot=snap,snapshot_provider=lambda:snap,clock=lambda:now[0],runtime_builder=builder)
   self.assertIsInstance(router._for_target(oldtarget)[0].selection,StrategyAccountTargetService)
   self.assertEqual(router._for_target(target)[1]['selector_profile'],PROFILE_ID)
   self.assertEqual(router.current(),oldtarget)
   self.assertEqual(account.path.read_bytes(),before)
   from data.strategy_continuous32_upgrade import Continuous32ResearchUpgrade
   account.append(dict(event_id='ordinary-cash-only',kind='CASH_CONFIRM',amount='1000',cash_basis='TOTAL_UNINVESTED'),expected_revision=account.read()['revision'])
   self.assertEqual(router.current(),oldtarget)
   source='data/strategy_continuous32_upgrade.py';raw=(Path(__file__).resolve().parents[1]/source).read_bytes();(root/source).write_bytes(raw)
   package=dict(schema='CONTINUOUS32_RESEARCH_UPGRADE_V1',purpose='EXPLICIT_SAME_MONTH_RESEARCH_VERSION_UPGRADE_NOT_MONTHLY_PUBLICATION',target_month='2026-11',upgrade_event_id='reviewed-upgrade',previous_target_id=oldtarget['target_id'],account_revision=account.read()['revision'],original_configuration_sha256=sha256(canonical(old)).hexdigest(),upgraded_configuration=dict(path='runtime.json',sha256=sha256((root/'runtime.json').read_bytes()).hexdigest()),reviewed_training=dict(path=old['training_manifest'],sha256=old['training_sha256'],closed_at=old['training_closed_at']),source_hashes={source:sha256(raw).hexdigest()},base_snapshot=snap,upgrade_archive=dict(path='both-archive.json',sha256=both))
   digest=put('upgrade.json',package)
   from data.strategy_continuous32_upgrade import upgrade_snapshot_provider
   checked=upgrade_snapshot_provider(root=root,package_path='upgrade.json',package_sha256=digest,base_provider=lambda:snap,clock=lambda:now[0],validate_code=runtime.selection._pins)
   router._snapshot_provider=checked
   from data.strategy_upgrade_package_materializer_v1 import materialize_current_upgrade
   server_ref=dict(path='server-reference.json',sha256=put('server-reference.json',dict(schema='UNIFIED_REVIEWED_DOMAIN_SERVER_PREPARATION_V6',upgrade=dict(path='upgrade.json',sha256=digest))))
   for level,schema,base in [(7,'SESSION_GUARDED_UNIFIED_PREPARATION_V7','base_v6'),(8,'OBSERVED_UNIFIED_PREPARATION_V8','base_v7'),(9,'SNAPSHOT_VALUATION_UNIFIED_PREPARATION_V9','base_v8'),(10,'LATEST_DISPLAY_UNIFIED_PREPARATION_V10','base_v9')]:
    server_path=f'server-v{level}.json';server_ref=dict(path=server_path,sha256=put(server_path,dict(schema=schema,**{base:server_ref},source_pins={})))
   from copy import deepcopy
   changed_target=deepcopy(oldtarget);changed_target['target_id']='f'*64
   with patch.object(router,'current',return_value=changed_target):
    with self.assertRaisesRegex(ValueError,'REVIEWED_TARGET_CHANGED'):
     materialize_current_upgrade(monthly=router,template_reference=dict(path='upgrade.json',sha256=digest),new_event_id='changed-target-event',output_directory='target-race-preparation',server_reference=server_ref,validate_sources=runtime.selection._pins)
   self.assertFalse((root/'target-race-preparation').exists())
   before_materialize=account.path.read_bytes()
   materialized=materialize_current_upgrade(monthly=router,template_reference=dict(path='upgrade.json',sha256=digest),new_event_id='new-reviewed-upgrade',output_directory='new-preparation',server_reference=server_ref,validate_sources=runtime.selection._pins)
   import json
   new_package=json.loads((root/materialized['package_reference']['path']).read_bytes())
   self.assertEqual(new_package['account_revision'],account.read()['revision'])
   self.assertEqual(new_package['previous_target_id'],oldtarget['target_id'])
   server_cursor=materialized['proposed_server_reference']
   for level in (10,9,8,7):
    server_bytes=(root/server_cursor['path']).read_bytes();self.assertEqual(sha256(server_bytes).hexdigest(),server_cursor['sha256'])
    server_document=json.loads(server_bytes);server_cursor=server_document[f'base_v{level-1}']
   self.assertEqual(json.loads((root/server_cursor['path']).read_bytes())['upgrade'],materialized['package_reference'])
   self.assertEqual(account.path.read_bytes(),before_materialize)
   self.assertTrue((root/'new-preparation/complete.json').exists())
   self.assertFalse((root/'data/strategy_account/research_upgrades'/materialized['package_reference']['sha256']).exists())
   with self.assertRaisesRegex(ValueError,'OUTPUT_EXISTS'):
    materialize_current_upgrade(monthly=router,template_reference=dict(path='upgrade.json',sha256=digest),new_event_id='another-event',output_directory='new-preparation',server_reference=server_ref,validate_sources=runtime.selection._pins)
   count=[0]
   def drift_gate():
    runtime.selection._pins();count[0]+=1
    if count[0]==2:
     account.append(dict(event_id='cash-race',kind='CASH_CONFIRM',amount='1000',cash_basis='TOTAL_UNINVESTED'),expected_revision=account.read()['revision'])
   with self.assertRaisesRegex(ValueError,'SNAPSHOT_CHANGED'):
    materialize_current_upgrade(monthly=router,template_reference=dict(path='upgrade.json',sha256=digest),new_event_id='race-event',output_directory='race-preparation',server_reference=server_ref,validate_sources=drift_gate)
   self.assertFalse((root/'race-preparation').exists())
   self.assertEqual(len(list(root.glob('.race-preparation.preparing-*/failed.json'))),1)
   # Current account changed only by the deliberate fixture race: bind template
   # again for the following existing real preflight assertions.
   package['account_revision']=account.read()['revision'];digest=put('upgrade.json',package)
   router._snapshot_provider=upgrade_snapshot_provider(root=root,package_path='upgrade.json',package_sha256=digest,base_provider=lambda:snap,clock=lambda:now[0],validate_code=runtime.selection._pins)
   upgrade=Continuous32ResearchUpgrade(monthly=router,package_path='upgrade.json',package_sha256=digest,validate_code=runtime.selection._pins)
   before_upgrade=account.path.read_bytes()
   with self.assertRaisesRegex(ValueError,'EXPLICIT_UPGRADE_EVENT_REQUIRED'):upgrade.execute(event_id='cash')
   evidence_dir=root/'data/strategy_account/research_upgrades'/digest
   with patch.object(upgrade,'_capture',side_effect=OSError('source offline')):
    with self.assertRaises(OSError):upgrade.execute(event_id='reviewed-upgrade')
   self.assertFalse(evidence_dir.exists())
   from data.strategy_continuous32_target_service import StrategyContinuous32TargetService
   with patch.object(StrategyContinuous32TargetService,'select',side_effect=AssertionError('preflight cannot select')):
    self.assertEqual(upgrade.preflight(event_id='reviewed-upgrade')['status'],'UPGRADE_SOURCE_PREFLIGHT_READY_NOT_EXECUTED')
   self.assertFalse(evidence_dir.exists())
   self.assertEqual(account.path.read_bytes(),before_upgrade)
   self.assertEqual(router.current(),oldtarget)
   transport.validate()
   with self.assertRaises(FileExistsError):materialize_transport_configuration(root=root,relative_path='transport.json',authorized=True)
   with (root/'data/strategy_account_action_capture_v3.py').open('ab') as stream:stream.write(b' ')
   with self.assertRaisesRegex(ValueError,'SOURCE_CHANGED'):transport.validate()

class UpgradeTransportCliTests(unittest.TestCase):
 def test_pair_required_and_receipt_reference(self):
  import contextlib,io,json
  import scripts.run_continuous32_upgrade_v3 as cli
  with TemporaryDirectory() as folder:
   base=['upgrade','--root',folder,'--configuration-path','base.json','--configuration-sha256','a'*64,'--package-path','upgrade.json','--package-sha256','b'*64,'--receipt-path','receipt.jsonl']
   with patch('sys.argv',base+['--action-transport-path','transport.json']),patch.object(cli,'run') as run,contextlib.redirect_stderr(io.StringIO()):
    with self.assertRaises(SystemExit):cli.main()
    run.assert_not_called()
   self.assertFalse((Path(folder)/'receipt.jsonl').exists())
   with patch('sys.argv',base+['--action-transport-path','transport.json','--action-transport-sha256','c'*64]),patch.object(cli,'run',return_value={'status':'FIXTURE_OFFLINE'}),contextlib.redirect_stdout(io.StringIO()):
    self.assertEqual(cli.main(),0)
   rows=[json.loads(line) for line in (Path(folder)/'receipt.jsonl').read_text().splitlines()]
   self.assertTrue(all(row['action_transport']=={'path':'transport.json','sha256':'c'*64} for row in rows))
