"""Create-only, source-bound full48 outer targets to 16 account inputs. No accounts."""
from pathlib import Path
from copy import deepcopy
import hashlib,json,os,re,shutil,types,traceback
ROOT=Path(__file__).resolve().parents[1];SOURCE=Path(__file__).resolve();LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
OUTPUT=ROOT/'data/cache/research/multidecision_account_inputs_20261003_v1'
CORE=ROOT/'backtest/ndx_multidecision_account_inputs_research.py';CORE_SHA='5f2edd4ebc8413d39c320f4f9dca781f30d0205d987d88b37b3d40e692fe9233'
LINEAGE=ROOT/'backtest/ndx_history_failed_lineage_guard_20261008.py';LINEAGE_SHA='fb72662a3739a1322afe5138856bd31f85328ae5e02bef02301756012f3ed77c'
OUTER_ROOT=ROOT/'data/cache/research/outer_lane_cutoff_refit_coordinator_20261008_v2'
OUTER_READER=ROOT/'scripts/ndx_outer_lane_refit_independent_readback_v2_20261008.py'
BOUND={
 'channels':('data/cache/research/bulk_long_window_channels_20261003_v1/channels.json','0f13e2cca5979608d742bfe1bf7a04c46ee9ca4396e5f45f22741420ee540516'),
 'price_publication':('data/cache/research/bulk_long_window_channels_20261003_v1/publication.json','b6c172eb6916361e9a701b8aed31f0caacb7161d6fdf1056d6c6127183343731'),
 'price_readback':('DYNAMIC_BULK_LONG_WINDOW_CHANNELS_INDEPENDENT_READBACK_20261003.json','3b7b35a3574757c9cdd12c74e701366979e490f5aadebcf0019da97349f4da65'),
 'price_reader':('scripts/ndx_bulk_long_window_channels_independent_review_20261003.py','7227e3705b12782c9514d39df7b23f12b1ae10e8da775f7364796d7c83ddcc99'),
 'outer_result':('data/cache/research/outer_lane_cutoff_refit_coordinator_20261008_v2/result.json','bceefa2a4f725bb2fe6166f9048494f47f7bd364234d1acad018c59a68ed0916'),
 'outer_coordinator':('scripts/ndx_outer_lane_refit_coordinator_v2_20261008.py','813508aca24a013e50805d4c4d0a375bae52ae5903af474ab865c35b3c18a522'),
 'account_contract':('research_contracts/multidecision_stateful_account_inputs_20261003_v1.json','3b657ea472b0098fc4ac22043f9b4ba5406caf363848dbf5c7fe3af626d8517c')}
OUTER_FLAGS=('point_in_time_verified','promotion_allowed','execution_authorized','account_executed','scoring_weights_used','automatic_retry_allowed','formal_benchmark_passed','source_bytes_authenticated')
FLAGS=dict.fromkeys(('source_bytes_authenticated','account_simulation_performed','fit_performed','selection_performed','execution_authorized','promotion_allowed','point_in_time_verified','formal_benchmark_passed','automatic_retry_allowed'),False)

def require(x,m):
 if not x:raise ValueError(m)
def enc(x):return json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(b):return hashlib.sha256(b).hexdigest()
def exact(a,b,m):require(enc(a)==enc(b),m)
def reference(p,h):return dict(path=str(Path(p).resolve()),sha256=h)
def valid(r):require(type(r)is dict and set(r)=={'path','sha256'} and type(r['path'])is str and Path(r['path']).is_absolute() and type(r['sha256'])is str and re.fullmatch('[a-f0-9]{64}',r['sha256']),'Explicit immutable absolute reference')
def merge(s,r):
 valid(r);require(r['path'] not in s or s[r['path']]==r['sha256'],'Conflicting source declaration');s[r['path']]=r['sha256']
def claims(s,obj):
 for p,h in obj.get('source_hashes',{}).items():merge(s,dict(path=p,sha256=h))
def decode(raw):
 def pairs(items):
  out={}
  for k,v in items:require(k not in out,'Duplicate JSON key');out[k]=v
  return out
 return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda x:(_ for _ in ()).throw(ValueError(x)))
def load(r,s,json_body=True):
 valid(r);p=Path(r['path']);require(not (p.parent/'failure.json').exists(),'Failed parent namespace')
 raw=p.read_bytes();require(sha(raw)==r['sha256'],'Consumed bytes differ from external anchor');merge(s,r)
 return decode(raw) if json_body else raw

def hashfile(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1024**2),b''):h.update(b)
 return h.hexdigest()
def lineage_members(sources):
 raw=LINEAGE.read_bytes();require(sha(raw)==LINEAGE_SHA,'Fixed diagnostic helper bytes')
 module=types.ModuleType('_fixed_history_failed_lineage');module.__file__=str(LINEAGE)
 exec(compile(raw,str(LINEAGE),'exec'),module.__dict__)
 return module.diagnostic_members(sources)

def guard(s):
 require(hashfile(SOURCE)==LOADED,'Loaded publisher drift')
 diagnostic=lineage_members(s)
 for p,h in s.items():require((p in diagnostic or not (Path(p).parent/'failure.json').exists()) and hashfile(p)==h,'Source drift/failure '+p)
def resource(size=0):
 p=OUTPUT.parent
 while not p.exists():p=p.parent
 require(shutil.disk_usage(p).free>=5*1024**3+size,'RESOURCE_STOP_BEFORE_WRITE')
def save(name,value,emergency=False):
 raw=enc(value)
 if not emergency:resource(len(raw))
 p=OUTPUT/name
 with p.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
 require(p.read_bytes()==raw,'Output write drift');return reference(p,sha(raw))
def private_core(s):
 r=reference(CORE,CORE_SHA);raw=load(r,s,False);m=types.ModuleType('_private_account_inputs');m.__file__=str(CORE);exec(compile(raw,str(CORE),'exec'),m.__dict__);return m

def load_envelope(refs,s,cache):
 """No producer/reader execution; authenticate original full direct/reuse bodies."""
 if set(refs)=={'references','numerical_reuse_references'}:
  e=load_envelope(refs['references'],s,cache);e['numerical_reuse_evidence']=load_envelope(refs['numerical_reuse_references'],s,cache);return e
 require(set(refs)=={'request','raw_result','postcheck','readback','reader'},'Exact five evidence roles')
 require(Path(refs['reader']['path']).resolve()==OUTER_READER.resolve(),'Fixed reviewed outer reader role')
 out={'references':deepcopy(refs)}
 for role,r in refs.items():
  if role=='reader':load(r,s,False);continue
  key=(r['path'],r['sha256'])
  if key not in cache:cache[key]=load(r,s)
  else:merge(s,r)
  out[role]=deepcopy(cache[key]);claims(s,out[role])
 return out

def outer_metadata(obj):
 for k in OUTER_FLAGS:require(obj[k] is False,'Outer metadata authority '+k)
def coordinator_inventory(expected):
 require(not (OUTER_ROOT/'failure.json').exists(),'Coordinator failed after initial load')
 require({str(p) for p in OUTER_ROOT.rglob('*') if p.is_file()}==set(expected),'Completed coordinator inventory drift')

def project_inputs(d,refs,outer_rows):
 contract=d['account_contract'];require(contract['schema']=='MULTIDECISION_STATEFUL_ACCOUNT_SOURCE_CONTRACT_V1','Explicit new source contract, not legacy no-flow objective')
 for k in FLAGS:require(contract[k] is False,'No source contract authority '+k)
 require(set(contract['benchmark_references'])=={'target_012922','original_8_incumbent'},'Two actual reference roles')
 execution=deepcopy(contract['execution_contract']);require('reference' not in execution,'No self-signed contract reference');execution['reference']=deepcopy(refs['account_contract'])
 return dict(outer_rows=deepcopy(outer_rows),price_evidence=dict(document=deepcopy(d['channels']),readback=deepcopy(d['price_readback']),references={k:deepcopy(refs[v]) for k,v in dict(channels='channels',publication='price_publication',readback='price_readback',reader='price_reader').items()}),execution_contract=execution,flows_by_lane=deepcopy(contract['flows_by_lane']),benchmark_references=deepcopy(contract['benchmark_references']))

def read_inputs():
 # Pending actual result/coordinator/contract rejects before any source IO.
 require(type(CORE_SHA)is str and re.fullmatch('[a-f0-9]{64}',CORE_SHA),'Core binding pending')
 require(all(type(h)is str and re.fullmatch('[a-f0-9]{64}',h) for _,h in BOUND.values()),'Actual outer terminal or new cash/account contract binding pending')
 refs={k:reference(ROOT/p,h) for k,(p,h) in BOUND.items()};sources={str(SOURCE):LOADED,str(LINEAGE):LINEAGE_SHA};docs={}
 for k,r in refs.items():
  v=load(r,sources,k not in ('price_reader','outer_coordinator'))
  if type(v)is dict:docs[k]=v;claims(sources,v)
 result=docs['outer_result'];require(result['schema']=='OUTER_LANE_FULL48_COORDINATOR_RESULT_V1' and result['status']=='COMPLETED_REGISTERED_COORDINATES' and result['failure'] is None,'Only completed full coordinate traversal, no partial selection')
 outer_metadata(result)
 require(type(result['rows'])is list and len(result['rows'])==48,'Complete original48 rows')
 started_path=OUTER_ROOT/'started.json';raw=started_path.read_bytes();started_ref=reference(started_path,sha(raw));started=decode(raw);merge(sources,started_ref);claims(sources,started)
 outer_metadata(started)
 require(started['schema']=='OUTER_LANE_FULL48_COORDINATOR_STARTED_V1' and type(started['coordinate_count'])is int and started['coordinate_count']==48,'Original coordinator started scope')
 require(started['source_hashes'].get(refs['outer_coordinator']['path'])==refs['outer_coordinator']['sha256'],'Started binds fixed coordinator version')
 # Started was not externally hash-anchored by result; explicitly retain this limit.
 receipt=load(started['receipt_contract_reference'],sources);require(receipt['schema']=='OUTER_LANE_RECEIPT_INTERFACE_CONTRACT_V1','Actual outer receipt contract')
 reader_ref=receipt['reader_reference'];require(Path(reader_ref['path']).resolve()==OUTER_READER.resolve(),'Receipt exact reader role');load(reader_ref,sources,False)
 prepared=load(result['prepared_reference'],sources);require(prepared['schema']=='OUTER_LANE_FULL48_INITIAL_PREPARATION_V1','Saved preparation role');require(len(prepared['prepared']['rows'])==48,'Saved initial48');outer_metadata(prepared)
 output=[];cache={};known_files={str(OUTER_ROOT/'result.json'),str(started_path),result['prepared_reference']['path']}
 for i,row in enumerate(result['rows']):
  require(type(row['coordinate_index'])is int and row['coordinate_index']==i,'Stable original coordinate order')
  initial=prepared['prepared']['rows'][i];exact([initial['cutoff'],initial['fx_mode'],initial['lane']],row['coordinate'],'Initial original coordinate')
  evidence=None
  if row['outcome'] in ('AUDITED_DIRECT_SUCCESS','AUDITED_NUMERICAL_REUSE','AUDITED_RISK_FAILURE','AUDITED_REUSED_RISK_FAILURE'):
   evidence=load_envelope(row['evidence_references'],sources,cache);exact(evidence['references']['reader'],reader_ref,'Common fixed receipt reader')
   exact(row['postcheck_reference'],evidence['references']['postcheck'],'Original coordinate post reference');exact(row['readback_reference'],evidence['references']['readback'],'Original coordinate audit reference')
   accepted=OUTER_ROOT/f'coordinates/{i:02d}-accepted.json';accepted_raw=accepted.read_bytes();require(decode(accepted_raw)==row,'Persisted accepted coordinate');merge(sources,reference(accepted,sha(accepted_raw)));known_files.add(str(accepted))
  else:require(row['outcome'] in ('SOURCE_BLOCKED','NO_REFIT_INPUT_OR_ADJACENT_PRIOR'),'Technical/unknown cannot be labelled complete inputs')
  for field in ('blocked_state_reference','dispatch_started_reference'):
   if field in row:
    v=load(row[field],sources);outer_metadata(v);require(type(v['coordinate_index'])is int and v['coordinate_index']==i,'Coordinate metadata location')
    if field=='blocked_state_reference':
     require(v['schema']=='OUTER_LANE_COORDINATE_NOT_DISPATCHED_V1','Blocked source role');item=v['prepared_row'];exact([item['cutoff'],item['fx_mode'],item['lane']],row['coordinate'],'Blocked original coordinate')
    else:
     require(v['schema']=='OUTER_LANE_COORDINATE_DISPATCH_STARTED_V1','Dispatch source role');exact(v['request']['coordinate'],row['coordinate'],'Dispatch original coordinate')
    known_files.add(row[field]['path'])
  output.append(dict(coordinate_index=i,coordinate=deepcopy(row['coordinate']),status=row['outcome'],evidence=evidence,coordinator_row_preserved=deepcopy(row)))
 coordinator_inventory(known_files)
 args=project_inputs(docs,refs,output)
 for r in args['benchmark_references'].values():load(r,sources,False)
 for flows in args['flows_by_lane'].values():
  for event in flows:load(event['source_reference'],sources,False)
 for row in docs['channels']['rows']:
  for role in ('raw_reference','receipt_reference'):merge(sources,row['channel'][role])
 core=private_core(sources)
 for engine in (core.FRACTIONAL_ENGINE,core.WHOLE_ENGINE):load(reference(ROOT/engine['path'],engine['sha256']),sources,False)
 guard(sources)
 return dict(args=args,core=core,sources=sources,input_references=refs,outer_started_reference=started_ref,outer_started_externally_anchored=False,coordinator_file_inventory=sorted(known_files))

def run(*,execute=False):
 require(execute is True,'Explicit research input preparation only');require(not OUTPUT.exists(),'Create only, retained failures prohibit retry')
 c=read_inputs();coordinator_inventory(c['coordinator_file_inventory']);resource();OUTPUT.mkdir(parents=True);written=[]
 try:
  written.append(save('started.json',dict(schema='MULTIDECISION_STATEFUL_ACCOUNT_INPUTS_STARTED_V1',input_references=c['input_references'],source_hashes=c['sources'],outer_started_reference=c['outer_started_reference'],outer_started_externally_anchored=False,**FLAGS)))
  guard(c['sources']);coordinator_inventory(c['coordinator_file_inventory']);result=c['core'].prepare_multidecision_account_inputs(**c['args'])
  rawref=save('inputs.json',dict(schema='MULTIDECISION_STATEFUL_ACCOUNT_INPUTS_DOCUMENT_V1',inputs=result,input_references=c['input_references'],source_hashes=c['sources'],outer_started_reference=c['outer_started_reference'],outer_started_externally_anchored=False,independent_readback_status='PENDING',**FLAGS),emergency=True);written.append(rawref)
  require(result['schema']=='MULTIDECISION_STATEFUL_ACCOUNT_INPUTS_V1' and type(result['coordinate_count'])is int and result['coordinate_count']==48 and result['lane_count']==8 and result['track_count']==16,'Full domain result')
  for k in c['core'].FLAGS:require(result[k] is False,'Result authority')
  guard(c['sources']);written.append(save('publication.json',dict(schema='MULTIDECISION_STATEFUL_ACCOUNT_INPUTS_PUBLICATION_V1',status='PUBLISHED_INPUTS_PENDING_INDEPENDENT_READBACK_NOT_ACCOUNTS',inputs_reference=rawref,started_reference=written[0],input_references=c['input_references'],source_hashes=c['sources'],**FLAGS)))
  guard(c['sources']);coordinator_inventory(c['coordinator_file_inventory'])
  for r in written:require(hashfile(r['path'])==r['sha256'],'Published output drift')
  require({p.name for p in OUTPUT.iterdir()}=={'started.json','inputs.json','publication.json'},'Exact output inventory');return rawref
 except BaseException as e:
  if not (OUTPUT/'failure.json').exists():save('failure.json',dict(status='FAILED_NO_RETRY',saved_references=written,error=dict(type=type(e).__name__,message=str(e),traceback=traceback.format_exc()),**FLAGS),emergency=True)
  raise

if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');print(json.dumps(run(execute=p.parse_args().execute)))
