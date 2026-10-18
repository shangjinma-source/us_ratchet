"""Independent signed-comparison arithmetic with a shared authenticated source adapter.

The fixed publisher's read-only load_inputs branch authenticates/project sources.
Neither its run function nor the comparison/metrics/account kernels are called.
Actual references are external arguments; missing anchors fail before source IO.
"""
import argparse
import hashlib
import json
import os
import re
import types
from pathlib import Path

SOURCE=Path(__file__).resolve()
ROOT=SOURCE.parents[1]
LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
PRODUCER=ROOT/'scripts/ndx_double_replacement_path_comparison_20261008.py'
PRODUCER_SHA=None
INSPECTOR=ROOT/'backtest/ndx_double_replacement_comparison_inspection_research.py'
INSPECTOR_SHA=None
PARENT=ROOT/'data/cache/research/double_replacement_path_comparison_20261008_v1'
OUTPUT=ROOT/'data/cache/research/double_replacement_path_comparison_independent_readback_20261008_v1'
FALSE=('account_executed','controls_executed','old_audits_reexecuted','fit_executed','selection_reexecuted','risk_recomputed','source_authenticated_by_pure','point_in_time_verified','promotion_allowed','formal_dual_benchmark_admission','fresh_oos_claimed','economic_winner_selected','currency_fx_equivalence_verified','automatic_retry_allowed')

def require(ok,message):
 if not ok:raise ValueError(message)
def encode(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(raw):return hashlib.sha256(raw).hexdigest()
def exact(a,b,message):require(encode(a)==encode(b),message)
def reference(value):
 require(type(value)is dict and set(value)=={'path','sha256'},'External reference required before IO')
 p,h=value['path'],value['sha256'];require(type(p)is str and p and type(h)is str and re.fullmatch('[0-9a-f]{64}',h),'External SHA anchor before IO')
 path=Path(p);require(path.is_absolute()and str(path)==p and '..'not in path.parts,'Canonical absolute source');return value
def flags(value):
 for key in FALSE:require(value[key]is False,'Exact false '+key)
def decode(raw):
 def unique(items):
  result={}
  for key,value in items:require(key not in result,'Duplicate JSON key');result[key]=value
  return result
 return json.loads(raw,object_pairs_hook=unique,parse_constant=lambda x:(_ for _ in ()).throw(ValueError('Nonfinite JSON')))
def take(ref,sources):
 reference(ref);p,h=ref['path'],ref['sha256'];require(p not in sources or sources[p]==h,'Source collision')
 raw=Path(p).read_bytes();require(sha(raw)==h,'Same authenticated consumed bytes');sources[p]=h;return raw
def filehash(path):
 digest=hashlib.sha256()
 with Path(path).open('rb')as stream:
  for block in iter(lambda:stream.read(1024**2),b''):digest.update(block)
 return digest.hexdigest()
def private(ref,sources):
 raw=take(ref,sources);module=types.ModuleType('_private_signed_comparison_readback_dependency');module.__file__=ref['path']
 exec(compile(raw,ref['path'],'exec'),module.__dict__);return module
def save(name,value):
 raw=encode(value);path=OUTPUT/name
 with path.open('xb')as target:target.write(raw);target.flush();os.fsync(target.fileno())
 require(path.read_bytes()==raw,'Saved own report bytes');return dict(path=str(path),sha256=sha(raw))
def diagnostic(error):
 try:message=str(error)
 except BaseException as secondary:message='ERROR_STRING_FAILED:'+type(secondary).__name__
 return dict(type=type(error).__name__,message=message)

def readback(*,registration_reference=None,comparison_reference=None,publication_reference=None,execute=False):
 require(execute is True,'Explicit independent readback')
 code_reference=dict(path=str(PRODUCER),sha256=PRODUCER_SHA)
 oracle_reference=dict(path=str(INSPECTOR),sha256=INSPECTOR_SHA)
 for value in (registration_reference,comparison_reference,publication_reference,code_reference,oracle_reference):reference(value)
 exact(comparison_reference['path'],str(PARENT/'comparison.json'),'Fixed comparison path')
 exact(publication_reference['path'],str(PARENT/'publication.json'),'Fixed publication path')
 require(not OUTPUT.exists(),'Create-only no retry')
 authenticated={str(SOURCE):LOADED};adapter=private(code_reference,authenticated)
 context=adapter.load_inputs(registration_reference,compile_comparison=False)
 require(context['pure'] is None,'Read-only adapter must not compile comparison or metrics')
 base=dict(context['sources'])
 require(base.get(str(PRODUCER))==PRODUCER_SHA,'Authenticated adapter own identity')
 for path,h in base.items():
  if path in authenticated:require(authenticated[path]==h,'Context source conflict')
  authenticated[path]=h
 document=decode(take(comparison_reference,authenticated));publication=decode(take(publication_reference,authenticated))
 raw_reference=document['raw_reference'];reference(raw_reference);exact(raw_reference['path'],str(PARENT/'raw_comparison.json'),'Fixed original return path')
 raw=decode(take(raw_reference,authenticated))
 started_reference=publication['started_reference'];reference(started_reference);exact(started_reference['path'],str(PARENT/'started.json'),'Fixed started path')
 started=decode(take(started_reference,authenticated))
 require(document['schema']=='SOURCE_BOUND_DOUBLE_REPLACEMENT_PATH_COMPARISON_V1','Comparison envelope schema')
 require(publication['schema']=='DOUBLE_REPLACEMENT_PATH_COMPARISON_PUBLICATION_V1'and publication['status']=='PUBLISHED_PENDING_INDEPENDENT_READBACK','Publication role')
 exact(publication['comparison_reference'],comparison_reference,'Published comparison bytes')
 exact(publication['raw_reference'],raw_reference,'Published original return')
 for obj in (document,publication,started):
  flags(obj);exact(obj['registration_reference'],registration_reference,'External registration role');exact(obj['source_hashes'],base,'Complete authenticated producer source union')
 for obj in (document,started):exact(obj['input_references'],context['refs'],'All twenty registered roles')
 require(started['schema']=='DOUBLE_REPLACEMENT_COMPARISON_STARTED_V1','Original comparison START schema')
 require(document['old_reference_metrics_recomputed'] is False and document['old_reference_source_claims_reaudited'] is False and document['audit_started_externally_anchored'] is False,'Preserved historical authentication scope')
 exact(document['shared_source_parser_role'],'AUTHENTICATED_SIGNED_PUBLISHER_IO_ONLY_COMPILE_NUMERICAL_FALSE','Source-only adapter role')
 exact(document['stream_summaries'],context['stream_summaries'],'Original full EOF and row-byte evidence')
 require(type(raw)is dict and set(raw)=={'call_invoked','call_count','returned','result','error','result_preserved_as_json'},'Complete original comparison return')
 require(raw['call_invoked']is True and type(raw['call_count'])is int and raw['call_count']==1 and raw['returned']is True and raw['result_preserved_as_json']is True and raw['error']is None,'Actual complete saved return, not exception')
 exact(raw['result'],document['comparison'],'Original raw result preserved')
 def guard():
  adapter.guard(context)
  require(filehash(SOURCE)==LOADED,'Loaded reader source drift')
  for path,h in authenticated.items():
   require(not (Path(path).parent/'failure.json').exists(),'Failed source namespace')
   require(filehash(path)==h,'Authenticated input/output drift')
  entries=list(PARENT.iterdir());exact(sorted(p.name for p in entries),['comparison.json','publication.json','raw_comparison.json','started.json'],'Exact complete publisher namespace')
  require(all(p.is_file()and not p.is_symlink()for p in entries),'Regular publisher files only')
 guard();OUTPUT.mkdir(parents=True,exist_ok=False);saved=[];completed=False
 try:
  saved.append(save('started.json',dict(schema='DOUBLE_REPLACEMENT_PATH_COMPARISON_READBACK_STARTED_V1',registration_reference=registration_reference,comparison_reference=comparison_reference,publication_reference=publication_reference,**dict.fromkeys(FALSE,False))))
  inspector=private(oracle_reference,authenticated)
  inspection=inspector.inspect_comparison(cases=context['cases'],expected_scenario_ids=context['expected_scenario_ids'],comparison=document['comparison'])
  require(inspection['status']=='PASS','Independent numeric inspection');completed=True
  guard()
  report=dict(schema='DOUBLE_REPLACEMENT_PATH_COMPARISON_INDEPENDENT_READBACK_V1',status='PASS',registration_reference=registration_reference,comparison_reference=comparison_reference,publication_reference=publication_reference,raw_reference=raw_reference,producer_started_reference=started_reference,producer_started_separate_external_anchor=False,reader_sha256=LOADED,source_hashes=authenticated,input_references=context['refs'],inspection=inspection,shared_source_authentication_adapter_reference=code_reference,independent_arithmetic_reference=oracle_reference,shared_source_authentication_and_case_projection=True,full_transitive_original_reference_sources_reaudited=False,source_bytes_authenticated=True,comparison_producer_called=False,comparison_metrics_called=False,signed_account_called=False,request_core_called=False,independent_old_reference_metrics_recomputed=False,arithmetic_inspection_completed=True,scope='INDEPENDENT_SIGNED_CANDIDATE_METRICS_AND_SAVED_THREE_REFERENCES_WITH_SHARED_AUTHENTICATED_SOURCE_PROJECTION_NOT_LEDGER_REPLAY',**dict.fromkeys(FALSE,False))
  saved.append(save('independent_readback.json',report));guard()
  for ref in saved:require(filehash(ref['path'])==ref['sha256'],'Final own output bytes')
  exact(sorted(p.name for p in OUTPUT.iterdir()),['independent_readback.json','started.json'],'Exact reader namespace')
  return saved[-1]
 except BaseException as error:
  save('failure.json',dict(schema='DOUBLE_REPLACEMENT_PATH_COMPARISON_READBACK_FAILURE_V1',status='FAILED_DO_NOT_RETRY_OR_CONSUME',error=diagnostic(error),arithmetic_inspection_completed=completed,saved_references=saved,registration_reference=registration_reference,comparison_reference=comparison_reference,publication_reference=publication_reference,**dict.fromkeys(FALSE,False)));raise

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true')
 for role in ('registration','comparison','publication'):parser.add_argument('--'+role);parser.add_argument('--'+role+'-sha')
 options=parser.parse_args()
 refs={role+'_reference':dict(path=getattr(options,role),sha256=getattr(options,role+'_sha'))for role in ('registration','comparison','publication')}
 print(json.dumps(readback(execute=options.execute,**refs)))
