"""Real publication/ready/CAS/selection with synthetic controlled source transports."""
from copy import deepcopy
from datetime import datetime,timedelta
from pathlib import Path
from hashlib import sha256
import json,re,unittest
from uuid import uuid4
from unittest.mock import patch
from core.strategy_account_ledger import canonical
from core.strategy_account_split_store_v1 import SplitStrategyAccountStore
from data.strategy_continuous32_target_decision import PROFILE_ID
from data.strategy_account_identity import PinnedStrategyIdentity
from data.strategy_account_action_capture import StrategyAccountActionCapture
from docs.candidates.strategy_account_split_market_capture import StrategyAccountMarketCapture
from data.current_quantity_v2_paper_action_sources import daily_url
from data.saved_frontier_monthly_view_v1 import SavedFrontierMonthlyView,SavedFrontierProposalStore
from docs.candidates import split_profiled_monthly_20261105 as module
from docs.candidates import split_monthly_factory_20261105 as factory
import test_strategy_account_monthly_release as fixture
ROOT=Path(__file__).resolve().parents[1]
def digest(raw):return sha256(raw).hexdigest()

class Tests(unittest.TestCase):
 def setUp(self):
  self.f=fixture.MonthlyReleaseTests();self.f.setUp();self.addCleanup(self.f.doCleanups);self.root=self.f.root
  self.now=datetime.fromisoformat('2026-12-01T15:00:00+00:00')
  self.pins={}
  from data.strategy_profiled_ready_release import PROFILE_ADMISSION_SOURCES
  for name in factory.RUNTIME_PATHS|module.base_release.RELEASE_PATHS|module.ADMISSION_PATHS|PROFILE_ADMISSION_SOURCES:
   raw=(ROOT/name).read_bytes();path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw);self.pins[name]=digest(raw)
  self.f.entry['runtime_pins']=self.pins
  self.f.identity['candidates'].append(dict(ticker='AAA',security_id='A',issuer_id='IA',status='READY_CONDITIONAL',identity_reviewed=True,identity_source_references=['synthetic-evidence.json']))
  self.f.entry['identity_sha256']=self.f.put('identity-release.json',self.f.identity)
  # Independent next-month source namespace; original files and receipts stay unchanged.
  originals={p.relative_to(self.root).as_posix():p.read_bytes() for p in self.root.rglob('*') if p.is_file() and p.suffix!='.py'}
  names={n:'january/'+n for n in originals}
  def shift(value,key=None):
   if isinstance(value,dict):return {names.get(k,k):shift(v,k) for k,v in value.items()}
   if isinstance(value,list):return [shift(v,key) for v in value]
   if type(value)is int and key in ('timestamp','date'):return value+31*86400
   if isinstance(value,str):
    if value in names:return names[value]
    value=re.sub(r'202[0-9]-[0-9]{2}-[0-9]{2}',lambda m:(datetime.fromisoformat(m[0])+timedelta(days=31)).date().isoformat(),value)
    if value=='2026-12':value='2027-01'
   return value
  objects={}
  for name,raw in originals.items():
   try:objects[name]=shift(json.loads(raw))
   except (ValueError,UnicodeDecodeError):pass
  bodies={n:canonical(v) for n,v in objects.items()}
  def hashes(value,mapping):
   if isinstance(value,dict):return {k:hashes(v,mapping) for k,v in value.items()}
   if isinstance(value,list):return [hashes(v,mapping) for v in value]
   return mapping.get(value,value) if isinstance(value,str) else value
  for _ in range(30):
   mapping={digest(originals[n]):digest(raw) for n,raw in bodies.items()}
   updated={n:canonical(hashes(obj,mapping)) for n,obj in objects.items()}
   if updated==bodies:break
   bodies=updated
  else:raise AssertionError('fixture hash graph cycle')
  for name,raw in originals.items():
   p=self.root/names[name];p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(bodies.get(name,raw))
  self.second=hashes(shift(deepcopy(self.f.entry)),mapping)
  self.entries=[];self.archive=[];self.approvals={}
  self.store=SplitStrategyAccountStore(self.root/'data/strategy_account/real_strategy.sqlite3',clock=lambda:self.now)
  self.store.initialize('real-strategy-account-v1',operation_id='init')
  identity=PinnedStrategyIdentity(self.root,'identity-release.json',self.f.entry['identity_sha256'])('AAA')
  self.store.append(dict(event_id='held-A',kind='DIRECT_FILL',security_id='A',side='BUY',quantity=2,price='80',fees='0',executed_at='2026-10-30T15:00:00+00:00',identity_evidence=identity),expected_revision=self.store.read()['revision'])
  self.action=dict(event_id='split-A',kind='SPLIT_CONFIRMED',action_id='split-A',security_id='A',ratio=8,effective_at='2026-11-01T12:00:00+00:00',broker_confirmed_at='2026-11-01T13:31:00+00:00',old_unit_id='old',new_unit_id='new',evidence_sha256='a'*64)
  self.store.append(self.action,expected_revision=self.store.read()['revision'])
  q='2026-11-01T13:30:00+00:00';proof=dict(schema='SPLIT_THREE_CLOCK_EXECUTION_CONTENT_V2',action_id='split-A',recorded_action_sha256=digest(canonical(self.action)),distribution_at=self.action['effective_at'],quote_unit_effective_at=q,broker_tradable_at=q,tradable_evidence_received_at='2026-11-01T13:32:00+00:00',tradable_evidence_semantics='OBSERVED_ACTUALLY_TRADABLE_NOT_FUTURE_NOTICE',clock_source_references={k:['timing'] for k in ('distribution_at','quote_unit_effective_at','broker_tradable_at','tradable_evidence_received_at')})
  calendar=dict(schema='FIXED_EXCHANGE_SESSIONS_V1',exchange='NASDAQ',sessions=[dict(date='2026-11-01',open=q,close='2026-11-01T20:00:00+00:00')])
  self.timing=dict(review=proof,source_hex={'timing':b'controlled observed tradability'.hex()},source_hashes={'timing':digest(b'controlled observed tradability')},calendar=calendar,calendar_sha256=digest(canonical(calendar)))
  self.store.append(dict(event_id='cash',kind='CASH_CONFIRM',amount='2000',cash_basis='TOTAL_UNINVESTED'),expected_revision=self.store.read()['revision'])
  self.initial=dict(registry_path='empty-registry.json',registry_sha256=self.put('empty-registry.json',dict(schema='REAL_STRATEGY_MONTHLY_RELEASES_V1',entries=[]))['sha256'],archive_path='empty-archive.json',archive_sha256=self.put('empty-archive.json',dict(schema='REAL_STRATEGY_RUNTIME_ARCHIVE_V1',entries=[]))['sha256'])
  anchor=dict(revision=0,record_sha256=None,snapshot=dict(self.initial,revision=0))
  self.activation=module.SplitProfiledActivation(root=self.root,initial_snapshot=self.initial,validate_code=lambda:None,legacy_anchor=anchor,clock=lambda:self.now)
 def put(self,name,value):
  raw=canonical(value);p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw);return dict(path=name,sha256=digest(raw))
 def market(self,**kw):
  def fetch(ticker):
   opening=self.now.replace(hour=14,minute=30);times=[int(opening.timestamp())+60*i for i in range(30)]
   return canonical(dict(chart=dict(error=None,result=[dict(meta=dict(symbol=ticker,currency='USD',instrumentType='EQUITY',exchangeTimezoneName='America/New_York',dataGranularity='1m',regularMarketPrice=10,regularMarketTime=int(self.now.timestamp()),currentTradingPeriod=dict(regular=dict(start=int(opening.timestamp()),end=int(opening.timestamp())+23400))),timestamp=times,indicators=dict(quote=[dict(open=[10]*30,high=[11]*30,low=[9]*30,close=[10]*30,volume=[10]*30)]))])))
  return StrategyAccountMarketCapture(fetch=fetch,**kw)
 def actions(self,**kw):
  def fetch(ticker,start,end):return dict(status=200,url=daily_url(ticker,start,end),body=canonical(dict(chart=dict(error=None,result=[dict(meta=dict(symbol=ticker,currency='USD',instrumentType='EQUITY'),events=({'splits':{str(int(datetime.fromisoformat(self.timing['review']['quote_unit_effective_at']).timestamp())):dict(date=int(datetime.fromisoformat(self.timing['review']['quote_unit_effective_at']).timestamp()),numerator=8,denominator=1,splitRatio='8:1')}} if ticker=='AAA' else {}))]))))
  rss=('<rss><channel><title>Nasdaq</title><item><title>Unrelated</title><pubDate>'+self.now.strftime('%a, %d %b %Y %H:%M:%S GMT')+'</pubDate></item></channel></rss>').encode()
  return StrategyAccountActionCapture(fetch=fetch,rss_fetch=lambda:dict(status=200,body=rss),**kw)
 def prepare(self,entry,label):
  self.entries.append(deepcopy(entry))
  original_registry=self.put(label+'/registry.json',dict(schema='REAL_STRATEGY_MONTHLY_RELEASES_V1',entries=self.entries))
  config=module.resolve_original(root=self.root,registry_path=original_registry['path'],registry_sha256=original_registry['sha256'],clock=lambda:self.now,account_state=self.store.read())
  original_config=self.put(label+'/original-runtime.json',config)
  self.archive.append(dict(configuration_path=original_config['path'],configuration_sha256=original_config['sha256']))
  original_archive=self.put(label+'/original-archive.json',dict(schema='REAL_STRATEGY_RUNTIME_ARCHIVE_V1',entries=[e for e in self.archive if json.loads((self.root/e['configuration_path']).read_bytes())['schema']=='REAL_STRATEGY_RUNTIME_V1']))
  config=dict(config,schema='REAL_STRATEGY_CONTINUOUS32_RUNTIME_V1',selector_profile=PROFILE_ID)
  configref=self.put(label+'/runtime.json',config)
  self.archive.append(dict(configuration_path=configref['path'],configuration_sha256=configref['sha256']))
  archive=self.put(label+'/archive.json',dict(schema='PROFILED_STRATEGY_RUNTIME_ARCHIVE_V1',entries=self.archive))
  registry=self.put(label+'/profile-registry.json',dict(schema='PROFILED_MONTHLY_RELEASES_V1',original_registry=original_registry,profiles=[dict(target_month=e['target_month'],selector_profile=PROFILE_ID) for e in self.entries]))
  reviewref=self.put(label+'/training-review.json',dict(schema='SPLIT_MONTHLY_TRAINING_UNITS_CONTENT_V1',manifest_sha256=config['training_sha256'],actions={'split-A':dict(scope='CARRIED_NONCANDIDATE',recorded_action_sha256=digest(canonical(self.action)),timing_sha256=digest(canonical(self.timing)))}))
  approval=dict(schema='SPLIT_MONTHLY_EXECUTION_APPROVAL_V1',configuration_sha256=digest(canonical(config)),source_pins=self.pins,training_review=reviewref,timing_bundles={'split-A':self.timing})
  approvalref=self.put(label+'/approval.json',approval);self.approvals[digest(canonical(config))]=approval
  runtime=factory.build_runtime(root=self.root,configuration=config,approval_pins=self.pins,timing_bundles={'split-A':self.timing},training_review_bytes=(self.root/reviewref['path']).read_bytes(),training_review_sha256=reviewref['sha256'],clock=lambda:self.now,market_factory=self.market,action_factory=self.actions)
  evidence=runtime.selection.provider(self.store.read()) # actual source assembly; no search
  captures=list((self.root/'data/strategy_account/evidence').glob('*/complete.json'));complete=max(captures,key=lambda p:p.stat().st_mtime_ns)
  def ref(path):return dict(path=path.relative_to(self.root).as_posix(),sha256=digest(path.read_bytes()))
  unit=json.loads((complete.parent/'unit_review.json').read_bytes())
  base=self.put(label+'/base-ready.json',dict(status='READY_FOR_ACTIVATION_NOT_ACTIVATED',target_month=config['target_month'],account_id=self.store.read()['account_id'],account_revision=self.store.read()['revision'],finished_at=self.now.isoformat(),files=dict(registry=original_registry,archive=original_archive,runtime=original_config,unit_review=ref(complete.parent/'unit_review.json'),complete=ref(complete)),reviewed_at=unit['reviewed_at'],account_writes=False,service_activated=False,search_calls=0,orders_created=False))
  profile=self.put(label+'/profile-ready.json',dict(schema='PROFILED_READY_RELEASE_V1',status='READY_FOR_REVIEW_NOT_ACTIVATED',base_ready=base,registry=registry,archive=archive,runtime=configref))
  ready=self.put(label+'/ready.json',dict(schema=module.SCHEMA,status='READY_FOR_REVIEW_NOT_ACTIVATED',base_ready=profile,approval=approvalref))
  return ready
 def test_two_actual_monthly_selections_and_stale_ready(self):
  prior=None;artifact=ROOT/'tmp'/('split_profiled_monthly_'+uuid4().hex);artifact.mkdir()
  with patch('socket.socket.connect',side_effect=AssertionError('NETWORK_FORBIDDEN')):
   for label,entry,now in [('december',self.f.entry,'2026-12-01T15:00:00+00:00'),('january',self.second,'2027-01-01T15:00:00+00:00')]:
    self.now=datetime.fromisoformat(now);ready=self.prepare(entry,label)
    revision=self.activation.snapshot()['revision']
    adopted=self.activation.adopt(receipt_path=ready['path'],receipt_sha256=ready['sha256'],expected_release_revision=revision)
    self.assertEqual(adopted,self.activation.adopt(receipt_path=ready['path'],receipt_sha256=ready['sha256'],expected_release_revision=revision))
    router=module.SplitProfiledRouter(root=self.root,snapshot_provider=self.activation.snapshot,initial_snapshot=self.activation.snapshot(),approvals=self.approvals,clock=lambda:self.now,market_factory=self.market,action_factory=self.actions)
    view=SavedFrontierMonthlyView(monthly=router,proposals=SavedFrontierProposalStore(self.root/'data/strategy_account/proposals.sqlite3'),validate_sources=router.validate_current_target_pins)
    request=dict(event_id=label,reason='INITIAL' if prior is None else 'MONTHLY_SELECTION',expected_revision=self.store.read()['revision'],previous_target_id=prior)
    # Before first target a view validator cannot require an existing target.
    def source_gate():
     for name,expected in self.pins.items():
      self.assertEqual(digest((self.root/name).read_bytes()),expected)
      self.assertEqual(digest((ROOT/name).read_bytes()),expected)
    view.validate_sources=source_gate
    result=view.generate(**request);self.assertEqual(result,view.generate(**request))
    self.assertEqual(result['payload']['target_month'],now[:7]);self.assertEqual(result['payload']['decision']['core_calls'],1)
    (artifact/(label+'-target-proposal.json')).write_bytes(canonical(dict(target=result,account=self.store.read(),snapshot=self.activation.snapshot())))
    prior=result['target_id']
   self.store.append(dict(event_id='later-cash',kind='CASH_CONFIRM',amount='2100',cash_basis='TOTAL_UNINVESTED'),expected_revision=self.store.read()['revision'])
   with self.assertRaisesRegex(ValueError,'READY_ACCOUNT_REVISION_CHANGED'):module.validate_ready_release(root=self.root,receipt_path=ready['path'],receipt_sha256=ready['sha256'],account_state=self.store.read(),clock=lambda:self.now)
   self.assertEqual(self.activation.snapshot()['revision'],2)
  print('SYNTHETIC_MONTHLY_ARTIFACT='+str(artifact))
class LegacyTests(unittest.TestCase):
 def test_original_receipt_replayed_at_pre_split_prefix(self):
  import test_review_prepare_real_monthly_release as ready_fixture
  from scripts.review_prepare_real_monthly_release import run
  helper=ready_fixture.ReviewPrepareTests();helper.setUp();self.addCleanup(helper.doCleanups)
  root=helper.root;run(**helper.arguments)
  ready='reviewed-package/ready.json';readyhash=digest((root/ready).read_bytes())
  initial={k:helper.arguments[k] for k in ('registry_path','registry_sha256','archive_path','archive_sha256')}
  legacy=module.base_activation.MonthlyReleaseActivation(root=root,initial_snapshot=initial,validate_code=lambda:None,clock=lambda:helper.now)
  adopted=legacy.adopt(receipt_path=ready,receipt_sha256=readyhash,expected_release_revision=0)
  before=(root/ready).read_bytes()
  from data.strategy_account_split_migration_v1 import prepare_split_account
  destination=helper.store.path.with_name('prepared-split.sqlite3')
  prepare_split_account(source_path=helper.store.path,destination_path=destination,expected_revision=helper.store.read()['revision'])
  # Disposable fixture only: emulate the already-reviewed generation switch.
  helper.store.path.replace(helper.store.path.with_name('old-account.sqlite3'));destination.replace(helper.store.path)
  split=SplitStrategyAccountStore(helper.store.path,clock=lambda:helper.now)
  sid=next(s for s,q in split.read()['shares'].items() if q)
  helper.now+=timedelta(minutes=2)
  split.append(dict(event_id='after-adoption-split',kind='SPLIT_CONFIRMED',action_id='after-adoption',security_id=sid,ratio=2,effective_at=(helper.now-timedelta(seconds=30)).isoformat(),broker_confirmed_at=helper.now.isoformat(),old_unit_id='old',new_unit_id='new',evidence_sha256='a'*64),expected_revision=split.read()['revision'])
  split.append(dict(event_id='after-split-cash',kind='CASH_CONFIRM',amount='1000',cash_basis='TOTAL_UNINVESTED'),expected_revision=split.read()['revision'])
  resumed=module.LegacyPrefixActivation(root=root,initial_snapshot=initial,validate_code=lambda:None,clock=lambda:helper.now)
  self.assertEqual(resumed.snapshot()['revision'],adopted['revision']);self.assertEqual((root/ready).read_bytes(),before)
  self.assertEqual(split.read()['shares'][sid],2)
if __name__=='__main__':unittest.main()
