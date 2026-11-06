"""Validate a monthly-only registration with the formal V34 startup builder.

Does not activate, run application lifespan, restart services or install schedules.
"""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from data.strategy_unified_server_preparation_v34 import build_unified_server_preparation_v34
from data.roa_monthly_loader import RoaMonthlySelectionLoader


def prepare_publication(*,root,active,registration,output_directory):
 root=Path(root).resolve();checked={};configuration_closure={};final_gates=[]
 def path(name):
  p=Path(name)
  if p.is_absolute() or '..' in p.parts or ':' in str(name):raise ValueError('PATH_OUTSIDE_ROOT')
  p=(root/p).resolve()
  if not p.is_relative_to(root):raise ValueError('PATH_OUTSIDE_ROOT')
  return p
 def read(ref):
  raw=path(ref['path']).read_bytes()
  if sha256(raw).hexdigest()!=ref['sha256']:raise ValueError('SOURCE_CHANGED:'+ref['path'])
  checked[ref['path']]=ref['sha256'];return raw,json.loads(raw)
 def recheck():
  for name,digest in checked.items():
   if sha256(path(name).read_bytes()).hexdigest()!=digest:raise ValueError('SOURCE_CHANGED_DURING_GATE:'+name)
 active_raw,current=read(active)
 if current.get('schema')!='STRATEGY_SERVER_ACTIVE_V6':raise ValueError('ACTIVE_SCHEMA_INVALID')
 old_ref=dict(path=current['configuration_path'],sha256=current['configuration_sha256'])
 _,old=read(old_ref);_,proposal=read(registration)
 if proposal.get('status')!='PREPARED_NOT_ACTIVATED' or proposal.get('expected_active')!=active:raise ValueError('REGISTRATION_ACTIVE_BINDING')
 _,receipt=read(proposal['receipt']);_,new=read(proposal['configuration'])
 if old.get('schema')!='ROA_UNIFIED_PREPARATION_V34' or new.get('schema')!=old['schema']:raise ValueError('V34_REQUIRED')
 before=deepcopy(old);after=deepcopy(new)
 old_months=before['roa'].pop('monthly_selections',{});new_months=after['roa'].pop('monthly_selections',{})
 if before!=after:raise ValueError('NON_MONTHLY_CONFIGURATION_CHANGE')
 month=proposal['month']
 if month in old_months or set(new_months)!=set(old_months)|{month} or any(new_months[k]!=v for k,v in old_months.items()):raise ValueError('MONTH_REGISTRY_NOT_APPEND_ONLY')
 expected=dict(path=receipt['runtime_path'],sha256=receipt['runtime_sha256'])
 if receipt.get('status')!='PREPARED_VERIFIED_NOT_REGISTERED' or receipt['month']!=month or new_months[month]!=expected:raise ValueError('PACKAGE_REGISTRATION_CONFLICT')
 _,registry=read(dict(path=receipt['registry_proposal'],sha256=sha256(path(receipt['registry_proposal']).read_bytes()).hexdigest()))
 if registry!={month:expected}:raise ValueError('REGISTRY_RECEIPT_CONFLICT')
 _,artifact=read(expected)
 if artifact['decision_date']!=receipt['decision_date'] or artifact['effective_month']!=month:raise ValueError('MONTH_SCOPE_CONFLICT')
 loaded=RoaMonthlySelectionLoader(root=root,registry={month:expected})(artifact['first_execution_session'])
 checked.update(loaded['source_hashes'])
 originals=[name for name in loaded['source_hashes'] if name.replace('\\','/').endswith('/selection.source.json')]
 if len(originals)!=1:raise ValueError('ORIGINAL_SELECTION_REQUIRED')
 _,original=read(dict(path=originals[0],sha256=loaded['source_hashes'][originals[0]]))
 if original['selection_id']!=receipt['selection_id'] or any(original[k]!=loaded[k] for k in ('selection','weights','securities','decision_date','effective_month')):raise ValueError('RECEIPT_SELECTION_CONFLICT')
 for old_month,spec in old_months.items():
  _,prior_artifact=read(spec)
  prior=RoaMonthlySelectionLoader(root=root,registry={old_month:spec})(prior_artifact['first_execution_session'])
  checked.update(prior['source_hashes'])
 def collect_configuration(reference, visiting=None):
  visiting=set() if visiting is None else visiting
  name=reference['path']
  if name in visiting:raise ValueError('CONFIGURATION_CYCLE')
  if name in configuration_closure:
   if configuration_closure[name]!=reference['sha256']:raise ValueError('CONFIGURATION_HASH_CONFLICT')
   return
  _,document=read(reference);configuration_closure[name]=reference['sha256']
  for source,expected_hash in document.get('source_pins',{}).items():
   if source in checked and checked[source]!=expected_hash:raise ValueError('SOURCE_PIN_CONFLICT:'+source)
   if sha256(path(source).read_bytes()).hexdigest()!=expected_hash:raise ValueError('CODE_SOURCE_CHANGED:'+source)
   checked[source]=expected_hash
  for key,value in document.items():
   if key.startswith('base_') and isinstance(value,dict) and set(value)=={'path','sha256'}:
    collect_configuration(value,visiting|{name})
 for reference in (old_ref,proposal['configuration']):collect_configuration(reference)
 # Use exactly the builder called by api.strategy_server_mount_v9; not a weaker schema-only gate.
 for reference in (old_ref,proposal['configuration']):
  recheck()
  prepared=build_unified_server_preparation_v34(root=root,configuration_path=reference['path'],configuration_sha256=reference['sha256'])
  prepared['validate_code']()
  final_gates.append(prepared['validate_code'])
  recheck()
 output=path(output_directory)
 if output==root or any(output==path(n) or output in path(n).parents for n in checked):raise ValueError('OUTPUT_INPUT_OVERLAP')
 if output.exists():raise ValueError('OUTPUT_ALREADY_EXISTS')
 recheck();output.mkdir(parents=True)
 with (output/'rollback_active.json').open('xb') as stream:stream.write(active_raw)
 next_active=dict(current,configuration_path=proposal['configuration']['path'],configuration_sha256=proposal['configuration']['sha256'])
 with (output/'next_active.json').open('xb') as stream:stream.write(json.dumps(next_active,indent=2).encode())
 result=dict(status='VALIDATED_MONTH_REGISTRATION_NOT_ACTIVATED',month=month,expected_active=active,registration=registration,
  next_active=dict(path=(output/'next_active.json').relative_to(root).as_posix(),sha256=sha256((output/'next_active.json').read_bytes()).hexdigest()),
  rollback=dict(path=(output/'rollback_active.json').relative_to(root).as_posix(),sha256=sha256(active_raw).hexdigest()),source_hashes=checked,
  configuration_closure=configuration_closure,source_hash_scope='DECLARED_CONFIGURATION_CHAIN_PINS_AND_MONTH_ARTIFACTS_NOT_ALL_TRANSITIVE_DATA',
  full_startup_gate='V34_CURRENT_AND_PROPOSED',account_writes=False,account_writes_scope='NO_LEDGER_EVENTS_APPENDED',filesystem_read_only=False,
  constructor_effects='Formal builders may initialize auxiliary directories/caches; no application lifespan is entered or background task started' ,lifespan_started=False,active_changed=False,restart=False,
  activation_requirement='Rerun the complete formal V34 builder and validate_code plus expected-active CAS immediately before switch; receipt hashes alone do not cover every transitive data dependency and are not switch authorization.')
 for gate in final_gates:gate()
 recheck()
 with (output/'validated.json').open('xb') as stream:stream.write(json.dumps(result,indent=2).encode())
 recheck();return result

if __name__=='__main__':
 import argparse
 parser=argparse.ArgumentParser(description=__doc__)
 for field in ('active-path','active-sha256','registration-path','registration-sha256','output-directory'):parser.add_argument('--'+field,required=True)
 args=parser.parse_args()
 result=prepare_publication(root=Path(__file__).resolve().parents[2],active=dict(path=args.active_path,sha256=args.active_sha256),registration=dict(path=args.registration_path,sha256=args.registration_sha256),output_directory=args.output_directory)
 print(json.dumps(result,ensure_ascii=False))
