"""Uninstalled single-security rolling source runner; server clock, create-only runs."""
from copy import deepcopy
from datetime import datetime,timezone
from hashlib import sha256
import json
from pathlib import Path
from zoneinfo import ZoneInfo
from core.strategy_account_ledger import canonical
from data.strategy_daily_session_capture import capture_session,reject_links,require,stamp
from data.strategy_daily_continuity_normalizer import NORMALIZATION_CODE_PATHS
from data.strategy_daily_rolling_parent_v3 import previous_session_parent,normalize_with_archived_parent,pinned,bounded_read

V3_SOURCES=NORMALIZATION_CODE_PATHS|{'data/strategy_daily_rolling_parent_v3.py',
 'data/strategy_daily_rolling_runner_v3.py','scripts/run_daily_rolling_source_v3.py',
 'data/strategy_account_runtime.py','core/strategy_account_store.py','core/strategy_monthly_target_store.py'}


def run_rolling_sources(*,root,configuration_bytes,configuration_sha256,execute=False,
                       account_reader=None,target_reader=None,fetch_daily=None,fetch_official=None,clock=None):
 clock=clock or (lambda:datetime.now(timezone.utc));reject_links(root);root=Path(root).resolve()
 require(len(configuration_bytes)<=1024*1024 and sha256(configuration_bytes).hexdigest()==configuration_sha256,'ROLLING_CONFIG_CHANGED')
 config=json.loads(configuration_bytes)
 require(config['schema']=='SERVER_ROLLING_DAILY_SOURCE_V3','ROLLING_CONFIG_SCHEMA')
 require(V3_SOURCES<={r['path'] for r in config['source_pins']},'ROLLING_SOURCE_SCOPE')
 def source_check():
  for reference in config['source_pins']:
   raw=pinned(root,reference)
   if reference['path'] in V3_SOURCES:
    require(raw==(Path(__file__).resolve().parents[1]/reference['path']).read_bytes(),'ROLLING_EXECUTING_SOURCE_CHANGED')
  verified_capture=json.loads(pinned(root,config['capture_configuration']))
  pinned(root,verified_capture['calendar']);pinned(root,verified_capture['identity_review'])
  pinned(root,config['seed_receipt'])
 source_check()
 capture_raw=pinned(root,config['capture_configuration']);capture=json.loads(capture_raw)
 now=stamp(clock());today=now.astimezone(ZoneInfo('America/New_York')).date().isoformat()
 if today<config['first_execution_date']:return dict(status='WAIT_FIRST_EXECUTION_DATE',http_calls=0)
 calendar=json.loads(pinned(root,capture['calendar']));dates=[r['date'] for r in calendar['sessions']]
 seed=json.loads(pinned(root,config['seed_receipt']))
 require(config['first_execution_date'] in dates and dates.index(config['first_execution_date'])>0 and
  dates[dates.index(config['first_execution_date'])-1]==seed['execution_session']['date'],'ROLLING_SEED_START_MISMATCH')
 if today not in dates:return dict(status='WAIT_CALENDAR_SESSION',http_calls=0)
 session=calendar['sessions'][dates.index(today)]
 if now>=stamp(session['close']):return dict(status='WAIT_NEXT_SESSION',http_calls=0)
 directory=root/config['runs_root']/today;reject_links(directory)
 require(directory.resolve().is_relative_to(root),'ROLLING_RUN_OUTSIDE_ROOT')
 if directory.exists():
  terminal_path=directory/'terminal.json';reject_links(terminal_path)
  if not terminal_path.is_file():return dict(status='NEEDS_RECOVERY',reason='INCOMPLETE_ROLLING_RUN',http_calls=0)
  require(terminal_path.stat().st_size<=1024*1024,'ROLLING_TERMINAL_READ_BUDGET')
  terminal=json.loads(bounded_read(terminal_path))
  if terminal.get('status')!='DAILY_CONDITIONAL_PACKET_SAVED':return dict(status='NEEDS_RECOVERY',reason=terminal.get('reason'),http_calls=0)
  require(terminal['configuration_sha256']==configuration_sha256 and terminal['session']==today,'ROLLING_SAVED_BINDING_CHANGED')
  for key,name in (('receipt_reference','receipt.json'),('manifest_reference','source-paths.json')):
   require(terminal[key]['path']==(directory/name).relative_to(root).as_posix(),'ROLLING_SAVED_PATH_CHANGED')
  receipt=json.loads(pinned(root,terminal['receipt_reference']));manifest=json.loads(pinned(root,terminal['manifest_reference']))
  require(receipt['execution_session']==session and receipt.get('release_sha256')==seed.get('release_sha256'),'ROLLING_SAVED_POLICY_OR_SESSION_CHANGED')
  previous=calendar['sessions'][dates.index(today)-1]
  require(stamp(receipt['source_received_at'])<=stamp(receipt['available_at'])<=stamp(terminal['finished_at'])<=now
   and stamp(terminal['finished_at'])<stamp(session['close'])
   and stamp(receipt['source_received_at']).astimezone(ZoneInfo('America/New_York')).date().isoformat()==today,
   'ROLLING_SAVED_TIME_CHANGED')
  require(stamp(receipt['market_asof'])==stamp(previous['close']),'ROLLING_SAVED_ASOF_CHANGED')
  require(set(manifest)==set(receipt['source_sha256']) and 0<len(manifest)<=2000,'ROLLING_SAVED_DOMAIN_CHANGED')
  total=0
  for name,reference in manifest.items():
   require(reference['sha256']==receipt['source_sha256'][name] and reference['path']==(directory/'files'/(reference['sha256']+'.bin')).relative_to(root).as_posix(),'ROLLING_SAVED_SOURCE_CHANGED')
   raw=pinned(root,reference,maximum=32*1024*1024-total);total+=len(raw)
   if name==receipt['normalized_inputs_path']:
    require(json.loads(raw)['signal_date']==previous['date'],'ROLLING_SAVED_SIGNAL_DATE_CHANGED')
  return dict(status='EXISTING_DAILY_PACKET_VERIFIED',receipt_reference=terminal['receipt_reference'],http_calls=0)
 try:
  parent=previous_session_parent(root=root,calendar_reference=capture['calendar'],runs_root=config['runs_root'],
   accepted_configuration_sha256=set(config['accepted_prior_configuration_sha256'])|{configuration_sha256},
   seed_receipt_reference=config['seed_receipt'],seed_source_paths=config['seed_source_paths'],now=now)
 except ValueError as error:
  return dict(status='WAIT_PREVIOUS_SESSION_EVIDENCE',reason=str(error),http_calls=0)
 readiness=capture_session(root=root,configuration_bytes=capture_raw,configuration_sha256=config['capture_configuration']['sha256'],execute=False,clock=clock)
 if readiness['status'] not in ('DRY_RUN_NO_HTTP_NO_FILES','EXISTING_CAPTURE_REQUIRES_RECEIPT_REVIEW'):return readiness
 if not execute:return dict(status='DRY_RUN_NO_HTTP_NO_FILES',session=today,http_calls=0,parent=parent['provenance'])
 if account_reader is None or target_reader is None:
  from data.strategy_account_runtime import ScopedAccountStore
  from core.strategy_monthly_target_store import StrategyMonthlyTargetStore
  paths=[root/config[key] for key in ('account_database','target_database')]
  for path in paths:
   reject_links(path);require(path.resolve().is_relative_to(root) and path.is_file(),'ROLLING_DATABASE_REQUIRED')
  account_reader=ScopedAccountStore(paths[0]).read;target_reader=StrategyMonthlyTargetStore(paths[1]).current
 state,target=deepcopy(account_reader()),deepcopy(target_reader())
 if not state or not target:return dict(status='WAIT_ACCOUNT_OR_MONTHLY_TARGET',http_calls=0)
 require(state['account_id']==target['payload']['account_id']==config['account_id'],'ROLLING_ACCOUNT_MISMATCH')
 if target['payload']['target_month']!=today[:7]:return dict(status='WAIT_MONTHLY_TARGET',http_calls=0)
 needed={sid for sid,q in target['payload']['target_quantities'].items() if q>0}|{sid for sid,q in state['shares'].items() if q>0}
 needed.update(o['security_id'] for o in state['orders'].values() if o['status']=='OPEN' and o['remaining_quantity']>0)
 if needed!={capture['security']['security_id']}:return dict(status='WAIT_SECURITY_DOMAIN_CONFIGURATION',http_calls=0)
 directory.mkdir(parents=True,exist_ok=False)
 def save(name,raw):
  path=directory/name;path.parent.mkdir(parents=True,exist_ok=True)
  with path.open('xb') as stream:stream.write(raw if isinstance(raw,bytes) else canonical(raw))
  return dict(path=path.relative_to(root).as_posix(),sha256=sha256(path.read_bytes()).hexdigest())
 def check():
  source_check()
  require(account_reader()==state and target_reader()==target,'ROLLING_SNAPSHOT_CHANGED')
  current=stamp(clock());require(now<=current<stamp(session['close']) and current.astimezone(ZoneInfo('America/New_York')).date().isoformat()==today,'ROLLING_PUBLICATION_WINDOW_CHANGED')
  return current
 save('started.json',dict(configuration_sha256=configuration_sha256,session=today,parent=parent['provenance'],started_at=now.isoformat()))
 save('configuration.json',configuration_bytes);captured=None
 try:
  captured=capture_session(root=root,configuration_bytes=capture_raw,configuration_sha256=config['capture_configuration']['sha256'],execute=True,fetch_daily=fetch_daily,fetch_official=fetch_official,clock=clock)
  require(captured['status'] in ('CAPTURED_TWENTY_SESSIONS_UNIT_REVIEW_REQUIRED','EXISTING_CAPTURE_REQUIRES_RECEIPT_REVIEW'),'ROLLING_CAPTURE_NOT_READY')
  result=normalize_with_archived_parent(root=root,capture_directory=str(Path(capture['output_root'])/today),expected_configuration_sha256=config['capture_configuration']['sha256'],parent=parent,state=state,target=target,clock=clock)
  require(result['status']=='CONDITIONAL_DAILY_EVIDENCE_READY_POLICY_UNCHANGED',result.get('reason',result['status']))
  check();manifest={}
  for name,raw in result['files'].items():
   digest=sha256(raw).hexdigest();relative='files/'+digest+'.bin';path=directory/relative
   manifest[name]=dict(path=path.relative_to(root).as_posix(),sha256=digest) if path.exists() and path.read_bytes()==raw else save(relative,raw)
  check();receipt=save('receipt.json',result['receipt']);mapping=save('source-paths.json',manifest);finished=check()
  terminal=dict(status='DAILY_CONDITIONAL_PACKET_SAVED',session=today,configuration_sha256=configuration_sha256,receipt_reference=receipt,manifest_reference=mapping,finished_at=finished.isoformat(),parent=parent['provenance'],policy_approved=False,source_authenticated=False,coverage_complete=False,http_calls=captured.get('http_calls'))
 except Exception as error:
  terminal=dict(status='NEEDS_RECOVERY',session=today,configuration_sha256=configuration_sha256,reason=str(error),finished_at=stamp(clock()).isoformat(),http_calls=captured.get('http_calls') if isinstance(captured,dict) else None,policy_approved=False)
 save('terminal.json',terminal);return terminal
