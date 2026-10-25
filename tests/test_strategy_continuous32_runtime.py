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

class ContinuousRuntimeTests(unittest.TestCase):
 def test_monthly_selection_preview_and_profiled_archive(self):
  with TemporaryDirectory() as temp:
   original,_,now,root=fixtures.ProviderTests().fixture(temp)
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
    runtime=build_runtime(**kwargs);provider=runtime.execution_provider.__self__
    def fetch(ticker):
     start=int(now[0].replace(hour=14,minute=30,second=0).timestamp());last=int(now[0].timestamp())
     return canonical(dict(chart=dict(error=None,result=[dict(meta=dict(symbol=ticker,currency='USD',instrumentType='EQUITY',exchangeTimezoneName='America/New_York',dataGranularity='1m',regularMarketPrice=10,regularMarketTime=last,currentTradingPeriod=dict(regular=dict(start=start,end=start+23400))),timestamp=list(range(start,start+1800,60)),indicators=dict(quote=[dict(open=[10]*30,high=[11]*30,low=[9]*30,close=[10]*30,volume=[10]*30)]))])))
    provider.market=StrategyAccountMarketCapture(identity_resolver=PinnedStrategyIdentity(root,config['identity_manifest'],config['identity_sha256']),fetch=fetch,clock=lambda:now[0],max_mark_age=900)
    provider.actions=original.actions
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
   wrong=dict(config,selector_profile='unknown')
   with self.assertRaisesRegex(ValueError,'UNKNOWN_SELECTOR_PROFILE'):
    build_runtime(root=root,configuration=wrong,clock=lambda:now[0])

 def test_profiled_release_uses_real_publication_resolver(self):
  import test_strategy_account_monthly_release as fixtures_release
  from data.strategy_profiled_monthly_release import resolve_monthly_runtime
  from data.strategy_account_monthly_release import RELEASE_PATHS
  from datetime import datetime
  f=fixtures_release.MonthlyReleaseTests();f.setUp();self.addCleanup(f.doCleanups)
  pins=dict(f.entry['runtime_pins'])
  for name in RUNTIME_PATHS|RELEASE_PATHS:
   raw=(Path(__file__).resolve().parents[1]/name).read_bytes();dest=f.root/name
   dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw);pins[name]=sha256(raw).hexdigest()
  f.entry['runtime_pins']=pins
  reference=dict(path='original-registry.json',sha256=f.put('original-registry.json',f.registry))
  document=dict(schema='PROFILED_MONTHLY_RELEASES_V1',original_registry=reference,profiles=[dict(target_month='2026-12',selector_profile=PROFILE_ID)])
  digest=f.put('profiled-registry.json',document)
  clock=lambda:datetime.fromisoformat('2026-12-01T15:00:00+00:00')
  config=resolve_monthly_runtime(root=f.root,registry_path='profiled-registry.json',registry_sha256=digest,clock=clock)
  self.assertEqual(config['selector_profile'],PROFILE_ID)
  self.assertEqual(config['runtime_pins'],pins)
  document['profiles']=[];digest=f.put('missing-profile.json',document)
  with self.assertRaisesRegex(ValueError,'EXPLICIT_CURRENT_PROFILE_REQUIRED'):
   resolve_monthly_runtime(root=f.root,registry_path='missing-profile.json',registry_sha256=digest,clock=clock)
