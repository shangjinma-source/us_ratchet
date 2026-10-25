from pathlib import Path
from hashlib import sha256
from copy import deepcopy
import json,unittest
from core.strategy_account_ledger import canonical
from data.strategy_profiled_release_activation import ProfiledMonthlyReleaseActivation
from data.strategy_continuous32_target_decision import PROFILE_ID
from data.strategy_dynamic_source_gate import bind_dynamic_source_gate
from scripts.review_prepare_real_monthly_release import run
from data.strategy_profiled_server_preparation import SOURCES,build_preparation
from api.strategy_unified_composition import SOURCES as UNIFIED_SOURCES, create_unified_strategy_router
import test_review_prepare_real_monthly_release as fixtures

class SharedProfileDailyTests(unittest.TestCase):
  def setup_case(self):
    f=fixtures.ReviewPrepareTests();f.setUp();self.addCleanup(f.doCleanups);root=f.root
    pins=dict(f.f.entry['runtime_pins'])
    for name in UNIFIED_SOURCES:
     raw=(Path(__file__).resolve().parents[1]/name).read_bytes();dest=root/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw);pins[name]=sha256(raw).hexdigest()
    f.f.entry['runtime_pins']=pins
    base=run(**f.arguments)
    def put(name,value):
     raw=canonical(value);(root/name).write_bytes(raw);return dict(path=name,sha256=sha256(raw).hexdigest())
    def load(ref):return json.loads((root/ref['path']).read_bytes())
    base_ref=dict(path='reviewed-package/ready.json',sha256=sha256((root/'reviewed-package/ready.json').read_bytes()).hexdigest())
    original=load(base['files']['runtime']);config=dict(original,schema='REAL_STRATEGY_CONTINUOUS32_RUNTIME_V1',selector_profile=PROFILE_ID)
    config_ref=put('profile-runtime.json',config)
    registry=put('profile-registry.json',dict(schema='PROFILED_MONTHLY_RELEASES_V1',original_registry=base['files']['registry'],profiles=[dict(target_month='2026-12',selector_profile=PROFILE_ID)]))
    archive=load(base['files']['archive']);archive['schema']='PROFILED_STRATEGY_RUNTIME_ARCHIVE_V1';archive['entries'].append(dict(configuration_path=config_ref['path'],configuration_sha256=config_ref['sha256']))
    archive_ref=put('profile-archive.json',archive)
    receipt=dict(schema='PROFILED_READY_RELEASE_V1',status='READY_FOR_REVIEW_NOT_ACTIVATED',base_ready=base_ref,registry=registry,archive=archive_ref,runtime=config_ref)
    receipt_ref=put('profile-ready.json',receipt)
    gate=bind_dynamic_source_gate(root=root,source_pins=pins)
    initial={k:f.arguments[k] for k in ('registry_path','registry_sha256','archive_path','archive_sha256')}
    from data.strategy_account_release_activation import MonthlyReleaseActivation
    old=MonthlyReleaseActivation(root=root,initial_snapshot=initial,validate_code=gate,clock=lambda:f.now)
    old.adopt(receipt_path=base_ref['path'],receipt_sha256=base_ref['sha256'],expected_release_revision=0)
    oldrow=old.releases.current();oldbytes=old.releases.path.read_bytes()
    anchor=dict(revision=oldrow['revision'],record_sha256=sha256(canonical(oldrow)).hexdigest(),snapshot=old.snapshot())
    activation=ProfiledMonthlyReleaseActivation(root=root,initial_snapshot=initial,validate_code=gate,legacy_anchor=anchor,clock=lambda:f.now)
    self.assertEqual(activation.snapshot()['registry_path'],base['files']['registry']['path'])
    stale=dict(anchor,revision=0)
    blocked=ProfiledMonthlyReleaseActivation(root=root,initial_snapshot=initial,validate_code=gate,legacy_anchor=stale,clock=lambda:f.now)
    with self.assertRaisesRegex(ValueError,'LEGACY_MIGRATION_ANCHOR_CHANGED'):blocked.snapshot()
    activation.adopt(receipt_path=receipt_ref['path'],receipt_sha256=receipt_ref['sha256'],expected_release_revision=0)
    factory_ref=put('profile-server.json',dict(schema='PROFILED_SERVER_PREPARATION_V2',initial_snapshot=initial,source_pins=pins,legacy_anchor=anchor))
    prepared=build_preparation(root=root,configuration_path=factory_ref['path'],configuration_sha256=factory_ref['sha256'],clock=lambda:f.now)
    prepared['fixture_source_pins']=pins
    return f,prepared

  def test_shared_cash_target_and_enabled_daily_http(self):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from data.strategy_profiled_runtime import build_runtime
    f,prepared=self.setup_case();router=prepared['router']
    original_fetch=f.arguments['market_capture'].fetch
    def complete_minutes(ticker):
      body=json.loads(original_fetch(ticker))
      row=body['chart']['result'][0];opening=row['meta']['currentTradingPeriod']['regular']['start']
      row['timestamp']=list(range(opening,opening+1800,60))
      row['indicators']['quote']=[{key:[value[0]]*30 for key,value in row['indicators']['quote'][0].items()}]
      return canonical(body)
    f.arguments['market_capture'].fetch=complete_minutes
    def build(**kwargs):
      runtime=build_runtime(**kwargs)
      provider=runtime.execution_provider.__self__
      provider.market=f.arguments['market_capture']
      provider.actions=f.arguments['action_capture']
      return runtime
    router._builder=build
    disabled_config=dict(evidence=dict(configuration_path='unused-default-off.json',
        configuration_sha256='0'*64,archive_root=f.root/'dailyarchive'))
    def application(configuration):
      app=FastAPI()
      app.include_router(create_unified_strategy_router(monthly=router,validate_code=prepared['validate_code'],
          source_pins=prepared['fixture_source_pins'],clock=lambda:f.now,daily_configuration=configuration))
      keys=[(r.path,method) for r in app.routes if hasattr(r,'methods') for method in r.methods]
      self.assertEqual(len(keys),len(set(keys)))
      return app
    app=application(disabled_config)
    with TestClient(app) as client:
      response=client.post('/api/strategy-account/events',json=dict(expected_revision=router.accounts.read()['revision'],event=dict(event_id='cash',kind='CASH_CONFIRM',amount='100',cash_basis='AVAILABLE_AFTER_RESERVATIONS')))
      self.assertEqual(response.status_code,200,response.text)
      state=router.accounts.read()
      response=client.post('/api/strategy-account/target/generate',json=dict(event_id='initial',reason='INITIAL',expected_revision=state['revision'],previous_target_id=None))
      self.assertEqual(response.status_code,200,response.text)
      target=router.current();before=deepcopy(target)
      response=client.post('/api/strategy-account/events',json=dict(expected_revision=router.accounts.read()['revision'],event=dict(event_id='cash-again',kind='CASH_CONFIRM',amount='90',cash_basis='AVAILABLE_AFTER_RESERVATIONS')))
      self.assertEqual(response.status_code,200,response.text)
      self.assertEqual(router.current(),before)
      response=client.post('/api/strategy-daily-v3/preview',json=dict(expected_revision=router.accounts.read()['revision'],target_id=target['target_id']))
      self.assertEqual(response.status_code,200,response.text)
      self.assertEqual(response.json()['detail_status'],'DAILY_PREVIEW_DISABLED')
      self.assertEqual(router.current(),before)
      configuration=self.install_packet(f,prepared,target)
      state_before=router.accounts.read()
      with TestClient(application(configuration)) as enabled_client:
        response=enabled_client.post('/api/strategy-daily-v3/preview',json=dict(expected_revision=state_before['revision'],target_id=target['target_id']))
      self.assertEqual(response.status_code,200,response.text)
      self.assertEqual(response.json()['status'],'READY',response.text)
      self.assertEqual(response.json()['new_orders'][0]['side'],'BUY')
      self.assertEqual(router.current(),before)
      self.assertEqual(router.accounts.read(),state_before)

  def install_packet(self,f,prepared,target):
    from datetime import date,timedelta
    from data.strategy_daily_signal_verifier import POLICY,CODE_PATHS,ROOT
    from data.strategy_continuous32_target_decision import VERSION
    from test_current_quantity_v2_risk_overlays import fixture as history_fixture
    from data.strategy_daily_source_runner import RUNNER_CODE_PATHS
    root=f.root
    def put(name,obj):
      raw=canonical(obj);path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
      return dict(path=name,sha256=sha256(raw).hexdigest())
    days=[];day=date(2026,11,30)
    while len(days)<21:
      if day.weekday()<5:days.append(day.isoformat())
      day-=timedelta(days=1)
    days.reverse();window=days[-20:]
    sid=next(iter(target['payload']['target_quantities']));q=target['payload']['target_quantities'][sid]
    inputs=history_fixture({sid:[10]*20},quantities={sid:q})
    inputs.update(signal_date=window[-1],observed_at=window[-1]+'T16:00:00-05:00',session_dates=days)
    inputs['base_target'].update(monthly_decision_date='2026-11-02')
    inputs['session_close_times']['closes']={d:d+'T16:00:00-05:00' for d in days}
    inputs['histories'][sid]['units']['unit_asof']=window[-1]
    inputs['histories'][sid]['closes']=[dict(date=d,completed_at=d+'T16:00:00-05:00',close='10') for d in window]
    session=dict(date='2026-12-01',open='2026-12-01T09:30:00-05:00',close='2026-12-01T16:00:00-05:00')
    calendar=put('daily/calendar.json',dict(schema='FIXED_EXCHANGE_SESSIONS_V1',exchange='NASDAQ',sessions=[dict(date=d,open=d+'T09:30:00-05:00',close=d+'T16:00:00-05:00') for d in days]+[session]))
    release=put('daily/release.json',dict(schema='SERVER_DAILY_POLICY_RELEASE_V1',approved=True,fixture_only=True,policy_id=POLICY,approved_at='2026-01-01T00:00:00Z',calendar_sha256=calendar['sha256'],code_sha256={p:sha256((ROOT/p).read_bytes()).hexdigest() for p in CODE_PATHS},selector_profile=PROFILE_ID,selection_method=VERSION,continuous_iterations=32))
    files={'normalized.json':canonical(inputs),'raw.json':b'{"fixture_only":true}'}
    receipt=dict(schema='SERVER_REVIEWED_DAILY_EVIDENCE_V1',normalization_reviewed=True,unresolved_units=[],pending_rights=[],account_id=prepared['router'].accounts.read()['account_id'],account_revision=prepared['router'].accounts.read()['revision'],target_id=target['target_id'],release_sha256=release['sha256'],source_sha256={p:sha256(b).hexdigest() for p,b in files.items()},normalized_inputs_path='normalized.json',raw_source_paths=['raw.json'],market_asof=inputs['observed_at'],source_received_at='2026-12-01T14:00:00Z',available_at='2026-12-01T14:01:00Z',valid_from=session['open'],valid_until=session['close'],execution_session=session,research_observed_at_semantics='MARKET_ASOF_NOT_RECEIPT')
    parent=put('daily/parent.json',receipt)
    ticker=next(c['ticker'] for c in f.f.identity['candidates'] if c['security_id']==sid)
    security=dict(ticker=ticker,security_id=sid,currency='USD',exchangeName='NMS',instrumentType='EQUITY')
    identity=put('daily/identity.json',dict(schema='SERVER_CAPTURE_IDENTITY_V1',review_status='REVIEWED',security=security,fixture_only=True,identity_manifest='identity-release.json',identity_sha256=f.f.entry['identity_sha256']))
    capture=put('daily/capture.json',dict(identity_review=identity,security=security,calendar=calendar))
    pins=[]
    for name in RUNNER_CODE_PATHS:
      raw=(ROOT/name).read_bytes();path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw);pins.append(dict(path=name,sha256=sha256(raw).hexdigest()))
    config=put('daily/pipeline.json',dict(schema='SERVER_DAILY_SOURCE_PIPELINE_V1',source_pins=pins,capture_configuration=capture,parent_reference=parent,runs_root='daily/runs',account_id=receipt['account_id']))
    manifest={}
    for name,raw in files.items():
      digest=sha256(raw).hexdigest();path='daily/runs/2026-12-01/files/'+digest+'.bin';(root/path).parent.mkdir(parents=True,exist_ok=True);(root/path).write_bytes(raw);manifest[name]=dict(path=path,sha256=digest)
    rr=put('daily/runs/2026-12-01/receipt.json',receipt);mr=put('daily/runs/2026-12-01/source-paths.json',manifest)
    put('daily/runs/2026-12-01/terminal.json',dict(status='DAILY_CONDITIONAL_PACKET_SAVED',session='2026-12-01',configuration_sha256=config['sha256'],receipt_reference=rr,manifest_reference=mr,finished_at=receipt['available_at']))
    return dict(policy_execution_enabled=True,policy_id=POLICY,evidence=dict(configuration_path=config['path'],configuration_sha256=config['sha256'],archive_root=root/'dailyarchive',release_path=release['path'],trusted_release_sha256=release['sha256']))
