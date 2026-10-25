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
from api.strategy_unified_rolling_composition_v3 import SOURCES as UNIFIED_SOURCES, create_unified_rolling_strategy_router_v3 as create_unified_strategy_router
import test_review_prepare_real_monthly_release as fixtures

class UnifiedRollingProfileTests(unittest.TestCase):
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
      (f.root/'daily/rolling-runs/2026-12-01/terminal.json').rename(f.root/'daily/removed-terminal.json')
      with TestClient(application(configuration)) as waiting_client:
        response=waiting_client.post('/api/strategy-daily-v3/preview',json=dict(expected_revision=state_before['revision'],target_id=target['target_id']))
      self.assertEqual(response.status_code,200,response.text)
      self.assertEqual(response.json()['status'],'WAIT',response.text)
      self.assertEqual(response.json()['new_orders'],[])
      self.assertEqual(router.current(),before)
      self.assertEqual(router.accounts.read(),state_before)

  def install_legacy_fixture(self,f,prepared,target):
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
  def install_packet(self,f,prepared,target):
    """Build a real rolling packet from an explicitly approved isolated seed."""
    from datetime import datetime
    from data.strategy_daily_rolling_runner_v3 import run_rolling_sources,V3_SOURCES
    root=f.root
    old=self.install_legacy_fixture(f,prepared,target)
    def put(name,value):
      raw=value if isinstance(value,bytes) else canonical(value);path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
      return dict(path=name,sha256=sha256(raw).hexdigest())
    calendar=json.loads((root/'daily/calendar.json').read_bytes())
    receipt=json.loads((root/'daily/parent.json').read_bytes())
    manifest=json.loads((root/'daily/runs/2026-12-01/source-paths.json').read_bytes())
    for name,ref in manifest.items():put(name,(root/ref['path']).read_bytes())
    inputs=json.loads((root/'normalized.json').read_bytes());rows=calendar['sessions'][:20];days=[r['date'] for r in rows]
    sid=next(iter(inputs['histories']))
    inputs.update(signal_date=days[-1],session_dates=days,observed_at=rows[-1]['close'])
    inputs['session_close_times']['closes']={r['date']:r['close'] for r in rows}
    inputs['histories'][sid]['units']['unit_asof']=days[-1]
    inputs['histories'][sid]['closes']=[dict(date=r['date'],completed_at=r['close'],close='10') for r in rows]
    norm=put('daily/seed-inputs.json',inputs)
    receipt.update(normalized_inputs_path=norm['path'],market_asof=rows[-1]['close'],source_received_at='2026-11-30T13:00:00Z',available_at='2026-11-30T13:01:00Z',execution_session=calendar['sessions'][-2])
    receipt['source_sha256'][norm['path']]=norm['sha256'];seed=put('daily/rolling-seed.json',receipt)
    capture=json.loads((root/'daily/capture.json').read_bytes())
    pins=[dict(path=name,sha256=sha256((root/name).read_bytes()).hexdigest()) for name in sorted(V3_SOURCES)]
    capture.update(schema='SERVER_DAILY_SESSION_CAPTURE_V1',source_pins=pins,output_root='daily/rolling-capture')
    capture_ref=put('daily/rolling-capture.json',capture)
    config=dict(schema='SERVER_ROLLING_DAILY_SOURCE_V3',source_pins=pins,capture_configuration=capture_ref,first_execution_date='2026-12-01',seed_receipt=seed,seed_source_paths={p:p for p in receipt['source_sha256']},accepted_prior_configuration_sha256=[],runs_root='daily/rolling-runs',account_id=receipt['account_id'])
    cfg=put('daily/rolling-pipeline.json',config)
    rows=calendar['sessions'][-21:-1]
    security=capture['security'];body=canonical(dict(chart=dict(error=None,result=[dict(meta=dict(security,symbol=security['ticker'],exchangeTimezoneName='America/New_York'),timestamp=[int(datetime.fromisoformat(r['close']).timestamp()) for r in rows],indicators=dict(quote=[dict(close=[10]*20)],adjclose=[dict(adjclose=[10]*20)]))])))
    official=b'<rss version="2.0"><channel><title>Fixture</title><item><title>UNRELATED fixture notice</title><pubDate>Mon, 30 Nov 2026 12:00:00 GMT</pubDate><description>Fixture only</description></item></channel></rss>'
    result=run_rolling_sources(root=root,configuration_bytes=canonical(config),configuration_sha256=cfg['sha256'],execute=True,account_reader=prepared['router'].accounts.read,target_reader=prepared['router'].current,fetch_daily=lambda *a:dict(status=200,body=body),fetch_official=lambda:dict(status=200,body=official),clock=lambda:f.now)
    self.assertEqual(result['status'],'DAILY_CONDITIONAL_PACKET_SAVED',result)
    old['evidence'].update(configuration_path=cfg['path'],configuration_sha256=cfg['sha256'])
    return old
