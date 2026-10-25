"""Server-side dynamic security domain and all-or-nothing daily evidence assembly.

Identity evidence is not a unit review. New securities explicitly require their
own completed-window review; this module never manufactures a seed or release.
"""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from core.strategy_account_ledger import canonical,replay,require
from data.strategy_account_identity import PinnedStrategyIdentity
from data.strategy_daily_rolling_parent_v3 import pinned,bounded_read
from data.strategy_daily_session_capture import reject_links
from data.strategy_daily_evidence_rebind import rebind_reviewed_daily_evidence
from data.strategy_daily_session_capture import stamp
from backtest.current_quantity_v2_risk_overlays import _validated
from zoneinfo import ZoneInfo


def locate_unit_baseline_sources(*,root,evidence_root,binding):
 """Locate by exact saved source hashes/documents, never capture mtime."""
 root=Path(root).resolve();directory=root/evidence_root;reject_links(directory)
 require(directory.resolve().is_relative_to(root),'DOMAIN_EVIDENCE_PATH')
 candidates=sorted(directory.iterdir()) if directory.is_dir() else []
 require(len(candidates)<=500,'DOMAIN_EVIDENCE_SCAN_BUDGET')
 review_name=binding.get('documents',{}).get('unit_review')
 if not review_name:return {}
 for candidate in candidates:
  reject_links(candidate)
  complete=candidate/'complete.json'
  if not candidate.is_dir() or not complete.is_file():continue
  document=json.loads(bounded_read(complete,1024*1024))
  saved=document.get('source_hashes',{})
  if document.get('status')!='EVIDENCE_ASSEMBLED_NOT_EXECUTED' or not saved or any(
   binding['source_hashes'].get(name)!=digest for name,digest in saved.items()):continue
  if document.get('documents',{}).get('unit_review')!=review_name:continue
  review_path=(candidate/'unit_review.json').relative_to(root).as_posix()
  review=json.loads(pinned(root,dict(path=review_path,sha256=binding['source_hashes'][review_name]),maximum=8*1024*1024))
  mapping={review_name:review_path}
  names={name for unit in review['securities'].values() for name in unit['source_references']}
  for name in names:
   path=(candidate/'actions'/name.removeprefix('strategy-action-capture/')) if name.startswith('strategy-action-capture/') else root/name
   relative=path.relative_to(root).as_posix()
   pinned(root,dict(path=relative,sha256=binding['source_hashes'][name]),maximum=8*1024*1024)
   mapping[name]=relative
  return mapping
 return {}


def plan_security_domain(*,root,state,target,identity_reference,source_paths=None):
 require(replay(state['account_id'],[row['payload'] for row in state['events']])==state,'DOMAIN_ACCOUNT_REPLAY')
 payload=target['payload'];decision=payload['decision'];binding=decision['payload']['input_binding']
 require(sha256(canonical(payload)).hexdigest()==target['target_id'],'DOMAIN_TARGET_HASH')
 require(sha256(canonical(decision['payload'])).hexdigest()==decision['decision_id'] and
  sha256(canonical(binding)).hexdigest()==decision['payload']['input_id'],'DOMAIN_DECISION_HASH')
 require(payload['account_id']==state['account_id'],'DOMAIN_ACCOUNT_BINDING')
 require(payload['target_quantities']==decision['payload']['target_quantities'],'DOMAIN_TARGET_QUANTITIES')
 reasons={}
 for sid,quantity in payload['target_quantities'].items():
  require(type(quantity)is int and quantity>=0,'DOMAIN_TARGET_QUANTITY')
  if quantity:reasons.setdefault(sid,set()).add('MONTHLY_TARGET')
 for sid,quantity in state['shares'].items():
  if quantity:reasons.setdefault(sid,set()).add('ACTUAL_HOLDING')
 for order in state['orders'].values():
  if order['status']=='OPEN' and order['remaining_quantity']>0:reasons.setdefault(order['security_id'],set()).add('OPEN_ORDER')
 require(len(reasons)<=250,'DOMAIN_BUDGET')
 manifest=json.loads(pinned(root,identity_reference,maximum=8*1024*1024))
 resolver=PinnedStrategyIdentity(root,identity_reference['path'],identity_reference['sha256'])
 units_path=binding.get('documents',{}).get('unit_review');units=None
 source_paths=source_paths or {}
 if units_path and units_path in source_paths:
  units=json.loads(pinned(root,dict(path=source_paths[units_path],sha256=binding['source_hashes'][units_path]),maximum=8*1024*1024))
  require(units.get('schema')=='STRATEGY_TARGET_UNIT_REVIEW_V1' and units.get('status')=='CONDITIONAL_CURRENT_UNITS_REVIEWED'
   and units.get('unresolved')==[] and units.get('pending_rights')==[],'DOMAIN_UNIT_BASELINE_INVALID')
  require(units['account_revision']==binding['account_revision'] and
   units['training_manifest_sha256']==binding['source_hashes'][binding['documents']['training_manifest']]
   and stamp(units['reviewed_at'])<=stamp(payload['created_at']),'DOMAIN_UNIT_BASELINE_SNAPSHOT')
 entries={}
 for sid in sorted(reasons):
  rows=[row for row in manifest['candidates'] if row.get('security_id')==sid]
  require(len(rows)==1,'DOMAIN_IDENTITY_NOT_UNIQUE')
  evidence=resolver(rows[0]['ticker']);require(evidence['security_id']==sid,'DOMAIN_IDENTITY_CHANGED')
  recorded={row['payload']['identity_evidence']['ticker'] for row in state['events']
   if row['payload'].get('identity_evidence',{}).get('security_id')==sid}
  require(not recorded or recorded=={evidence['ticker']},'DOMAIN_RECORDED_TICKER_CHANGED')
  baseline=None
  if units and sid in units['securities']:
   unit=units['securities'][sid]
   require(unit['security_id']==sid and unit['current_price_basis']==binding['current_price_basis']
    and unit['historical_scenarios_usable_in_current_units'] is True and unit['held_quantities_in_current_units'] is True,
    'DOMAIN_UNIT_BASELINE_BINDING')
   require(unit['current_mark_sha256']==sha256(canonical(binding['marks'][sid])).hexdigest()
    and unit['training_manifest_sha256']==units['training_manifest_sha256'],'DOMAIN_UNIT_BASELINE_MARK')
   references={name:binding['source_hashes'][name] for name in unit['source_references']}
   for name,digest in references.items():pinned(root,dict(path=source_paths[name],sha256=digest),maximum=8*1024*1024)
   baseline=dict(review_reference=dict(path=units_path,sha256=binding['source_hashes'][units_path]),
    unit=deepcopy(unit),reviewed_at=units['reviewed_at'],source_hashes=references)
  entries[sid]=dict(security_id=sid,ticker=evidence['ticker'],identity=evidence,reasons=sorted(reasons[sid]),
   unit_baseline=baseline,status='FIRST_WINDOW_REVIEW_REQUIRED' if baseline else 'WAIT_UNIT_BASELINE')
 return dict(status='DOMAIN_PLANNED_NOT_CAPTURED',account_id=state['account_id'],account_revision=state['revision'],
  target_id=target['target_id'],securities=entries,policy_approved=False)


def aggregate_security_packets(*,domain,packets,state,target,now):
 """Consume independently hash-bound server packets; no partial-domain signal."""
 needed=set(domain['securities'])
 actual={sid for sid,q in target['payload']['target_quantities'].items() if q>0}|{sid for sid,q in state['shares'].items() if q>0}
 actual.update(o['security_id'] for o in state['orders'].values() if o['status']=='OPEN' and o['remaining_quantity']>0)
 require(needed==actual,'AGGREGATE_REQUIRED_DOMAIN_CHANGED')
 require(domain['account_id']==state['account_id'] and domain['account_revision']==state['revision']
  and domain['target_id']==target['target_id'],'AGGREGATE_SNAPSHOT_CHANGED')
 if set(packets)!=needed or any(packets[sid].get('receipt_bytes') is None for sid in needed):
  return dict(status='WAIT_COMPLETE_SECURITY_DOMAIN',receipt=None,files=None,missing=sorted(needed-set(packets)))
 require(bool(needed),'AGGREGATE_EMPTY_DOMAIN')
 files={};histories={};parents=[];template=None;receipt_template=None;signature=None;received=[];raw_paths=set()
 def include(name,raw):
  require(name not in files or files[name]==raw,'AGGREGATE_SOURCE_CONFLICT')
  files[name]=raw
  require(len(files)<=2000 and sum(map(len,files.values()))<=32*1024*1024,'AGGREGATE_SOURCE_BUDGET')
 for sid in sorted(needed):
  packet=packets[sid];raw=packet['receipt_bytes'];digest=sha256(raw).hexdigest()
  require(digest==packet['trusted_receipt_sha256'],'AGGREGATE_RECEIPT_HASH')
  receipt=json.loads(raw)
  require(receipt.get('schema')=='SERVER_REVIEWED_DAILY_EVIDENCE_V1','AGGREGATE_RECEIPT_SCHEMA')
  require(receipt['account_id']==state['account_id'],'AGGREGATE_ACCOUNT_CHANGED')
  require(receipt.get('normalization_reviewed') is True and receipt.get('unresolved_units')==[]
   and receipt.get('pending_rights')==[],'AGGREGATE_REVIEW_REQUIRED')
  require(set(packet['files'])==set(receipt['source_sha256']),'AGGREGATE_SOURCE_DOMAIN')
  for name,body in packet['files'].items():
   require(sha256(body).hexdigest()==receipt['source_sha256'][name],'AGGREGATE_SOURCE_HASH')
   include(name,body)
  inputs=json.loads(packet['files'][receipt['normalized_inputs_path']])
  raw_sources=receipt.get('raw_source_paths')
  require(type(raw_sources)is list and bool(raw_sources) and all(type(name)is str and
   name in packet['files'] and name!=receipt['normalized_inputs_path'] for name in raw_sources),
   'AGGREGATE_RAW_SOURCE_DOMAIN')
  require(set(inputs['histories'])=={sid},'AGGREGATE_SECURITY_MISMATCH')
  session=receipt['execution_session'];available=stamp(receipt['available_at'])
  require(receipt.get('research_observed_at_semantics')=='MARKET_ASOF_NOT_RECEIPT'
   and stamp(inputs['observed_at'])==stamp(receipt['market_asof'])
   and stamp(receipt['market_asof'])==stamp(inputs['session_close_times']['closes'][inputs['signal_date']])
   and stamp(receipt['market_asof'])<=stamp(receipt['source_received_at'])
   and stamp(receipt['valid_from'])==max(stamp(session['open']),available)
   and stamp(receipt['valid_until'])==stamp(session['close'])
   and session['date']==stamp(now).astimezone(ZoneInfo('America/New_York')).date().isoformat(),
   'AGGREGATE_SESSION_CLOCK')
  validation=deepcopy(inputs)
  validation['base_target']=dict(inputs['base_target'],quantities={sid:1},
   price_units={sid:inputs['histories'][sid]['units']['basis_id']})
  _validated(**validation,count=20)
  mark=(inputs['signal_date'],canonical(inputs['session_dates']),canonical(inputs['session_close_times']),
        receipt['market_asof'],canonical(receipt['execution_session']),receipt.get('release_sha256'))
  require(signature is None or signature==mark,'AGGREGATE_SESSION_OR_POLICY_MISMATCH')
  signature=mark;template=deepcopy(inputs);receipt_template=deepcopy(receipt)
  require(stamp(receipt['source_received_at'])<=stamp(receipt['available_at'])<=stamp(now)
   <stamp(receipt['execution_session']['close']),'AGGREGATE_TIME_INVALID')
  histories[sid]=deepcopy(inputs['histories'][sid]);received.append(stamp(receipt['source_received_at']))
  raw_paths.update(receipt['raw_source_paths'])
  name='aggregate-parents/'+digest+'.json';include(name,raw);parents.append(dict(security_id=sid,path=name,sha256=digest))
 template['histories']=histories
 template['base_target']['price_units']={sid:history['units']['basis_id'] for sid,history in histories.items()}
 name='aggregate-inputs/'+sha256(canonical(template)).hexdigest()+'.json';include(name,canonical(template))
 receipt_template.update(normalized_inputs_path=name,source_sha256={name:sha256(raw).hexdigest() for name,raw in files.items()},
  source_received_at=max(received).isoformat(),available_at=stamp(now).isoformat(),
  valid_from=max(stamp(now),stamp(receipt_template['execution_session']['open'])).isoformat(),
  source_authenticated=False,coverage_complete=False,aggregate_parents=parents)
 receipt_template['raw_source_paths']=sorted(raw_paths)
 result=rebind_reviewed_daily_evidence(receipt_bytes=canonical(receipt_template),trusted_receipt_sha256=sha256(canonical(receipt_template)).hexdigest(),files=files,state=state,target=target,now=stamp(now).isoformat())
 if result.get('receipt') is not None:
  # Frozen rebind intentionally emits only monthly-positive strategy histories.
  # Preserve an explicit independently hashed full domain for future rebinding
  # (held exits and pending orders must not disappear from evidence coverage).
  result['receipt']['full_domain_inputs_path']=name
  result['receipt']['full_domain_security_ids']=sorted(needed)
  result['status']='COMPLETE_DOMAIN_REBOUND_POLICY_UNCHANGED'
 return result
