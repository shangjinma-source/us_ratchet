"""Versioned frontier request domain; preserves frozen production source files."""
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

def plan_security_domain(*,root,state,target,identity_reference,source_paths=None,
                         monthly_quantities=None,extra_security_ids=()):
 require(replay(state['account_id'],[row['payload'] for row in state['events']])==state,'DOMAIN_ACCOUNT_REPLAY')
 payload=target['payload'];decision=payload['decision'];binding=decision['payload']['input_binding']
 require(sha256(canonical(payload)).hexdigest()==target['target_id'],'DOMAIN_TARGET_HASH')
 require(sha256(canonical(decision['payload'])).hexdigest()==decision['decision_id'] and
  sha256(canonical(binding)).hexdigest()==decision['payload']['input_id'],'DOMAIN_DECISION_HASH')
 require(payload['account_id']==state['account_id'],'DOMAIN_ACCOUNT_BINDING')
 require(payload['target_quantities']==decision['payload']['target_quantities'],'DOMAIN_TARGET_QUANTITIES')
 reasons={}
 for sid,quantity in (payload['target_quantities'] if monthly_quantities is None else monthly_quantities).items():
  require(type(quantity)is int and quantity>=0,'DOMAIN_TARGET_QUANTITY')
  if quantity:reasons.setdefault(sid,set()).add('MONTHLY_TARGET')
 for sid in extra_security_ids:
  require(type(sid)is str and bool(sid),'DOMAIN_EXTRA_SECURITY_ID')
  reasons.setdefault(sid,set()).add('MONTHLY_RISK_HISTORY')
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
