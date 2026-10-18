"""Create-only original-eight nominal account inputs; no account engine execution."""
from pathlib import Path
import hashlib,json,os,re,shutil,types,traceback
ROOT=Path(__file__).resolve().parents[1];SOURCE=Path(__file__).resolve();LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
OUTPUT=ROOT/'data/cache/research/multidecision_incumbent_inputs_20261003_v1'
CORE=ROOT/'backtest/ndx_multidecision_incumbent_inputs_research.py';CORE_SHA='c4a95ee8ecc61e9c8f803e0e1c72c3621bb587e4758b723722b279b1e8506a71'
BOUND={
 'original_inputs':('data/cache/research/original_eight_long_window_channels_20261003_v1/channels.json','67d433ae92acb0755a1ffdabf090e6c20706b4d1ba893637673e96a047acc372'),
 'original_publication':('data/cache/research/original_eight_long_window_channels_20261003_v1/publication.json','836622bff616370375539490c441fbb5b988d5dab8b661b202991288bcbf05e1'),
 'original_readback':('DYNAMIC_ORIGINAL_EIGHT_LONG_WINDOW_INDEPENDENT_READBACK_20261003.json','182e901ad1554292444142c51ace220da2f1912b361d048d78b499d5aeaeb988'),
 'original_reader':('scripts/ndx_original_eight_long_window_independent_review_20261003.py','738e876b8e03cc2d2892a34b2c254c4ea8cc91e191e03acca55d15110b4bd469'),
 'candidate_inputs':('data/cache/research/multidecision_account_inputs_20261003_v1/inputs.json',None),
 'candidate_publication':('data/cache/research/multidecision_account_inputs_20261003_v1/publication.json',None),
 'candidate_readback':('data/cache/research/multidecision_account_inputs_independent_readback_20261003_v1/independent_readback.json',None),
 'candidate_reader':('scripts/ndx_multidecision_account_inputs_independent_readback_20261003.py',None)}
FLAGS=dict.fromkeys(('source_bytes_authenticated','account_simulation_performed','fit_performed','selection_performed','execution_authorized','promotion_allowed','point_in_time_verified','formal_benchmark_passed','automatic_retry_allowed','weights_normalized','cross_lane_execution_reused'),False)

def require(x,m):
 if not x:raise ValueError(m)
def enc(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(b):return hashlib.sha256(b).hexdigest()
def reference(p,h):return dict(path=str(Path(p).resolve()),sha256=h)
def valid(r):require(type(r)is dict and set(r)=={'path','sha256'} and type(r['path'])is str and Path(r['path']).is_absolute() and type(r['sha256'])is str and re.fullmatch('[a-f0-9]{64}',r['sha256']),'Absolute immutable source reference')
def merge(s,r):
 valid(r);require(r['path'] not in s or s[r['path']]==r['sha256'],'Source conflict');s[r['path']]=r['sha256']
def claims(s,o):
 for p,h in o.get('source_hashes',{}).items():merge(s,dict(path=p,sha256=h))
def decode(b):
 def pairs(items):
  d={}
  for k,v in items:require(k not in d,'Duplicate JSON key');d[k]=v
  return d
 return json.loads(b,object_pairs_hook=pairs,parse_constant=lambda x:(_ for _ in ()).throw(ValueError(x)))
def load(r,s,body=True):
 valid(r);p=Path(r['path']);require(not (p.parent/'failure.json').exists(),'Failed parent namespace');b=p.read_bytes();require(sha(b)==r['sha256'],'Consumed source SHA mismatch');merge(s,r);return decode(b) if body else b
def hashfile(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1024**2),b''):h.update(b)
 return h.hexdigest()
def inventory(root,names):require({p.name for p in root.iterdir()}==set(names),'Parent or output namespace inventory drift')
def guard(s,parents):
 require(hashfile(SOURCE)==LOADED,'Loaded publisher drift')
 for p,h in s.items():require(not (Path(p).parent/'failure.json').exists() and hashfile(p)==h,'Source drift/failure')
 for p,names in parents.items():inventory(Path(p),names)
def resource(n=0):
 p=OUTPUT.parent
 while not p.exists():p=p.parent
 require(shutil.disk_usage(p).free>=5*1024**3+n,'Resource reserve')
def save(name,value,emergency=False):
 b=enc(value)
 if not emergency:resource(len(b))
 p=OUTPUT/name
 with p.open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
 require(p.read_bytes()==b,'Saved output bytes drift');return reference(p,sha(b))
def load_inputs():
 require(type(CORE_SHA)is str and re.fullmatch('[a-f0-9]{64}',CORE_SHA) and all(type(h)is str and re.fullmatch('[a-f0-9]{64}',h) for p,h in BOUND.values()),'Future candidate source bindings pending before IO')
 refs={k:reference(ROOT/p,h) for k,(p,h) in BOUND.items()};sources={str(SOURCE):LOADED};docs={};parents={}
 for k,r in refs.items():
  v=load(r,sources,not k.endswith('_reader'))
  if type(v)is dict:docs[k]=v;claims(sources,v)
 for prefix,filename in [('original','channels.json'),('candidate','inputs.json')]:
  directory=Path(refs[prefix+'_inputs']['path']).parent;parents[str(directory)]=['started.json',filename,'publication.json'];inventory(directory,parents[str(directory)])
  p=directory/'started.json';b=p.read_bytes();merge(sources,reference(p,sha(b)))
  # These old started bytes are observed in this read, not promoted to dispatch-time authority.
 require(docs['original_publication']['source_hashes']==docs['original_inputs']['source_hashes'],'Original source map publication')
 require(enc(docs['candidate_publication']['source_hashes'])==enc(docs['candidate_inputs']['source_hashes']),'Candidate source map publication')
 for row in docs['original_inputs']['rows']:
  for role in ('raw_reference','receipt_reference'):load(row['channel'][role],sources,False)
 corebytes=load(reference(CORE,CORE_SHA),sources,False);core=types.ModuleType('_private_original_eight_input_adapter');core.__file__=str(CORE);exec(compile(corebytes,str(CORE),'exec'),core.__dict__)
 engine=core.ENGINE;load(reference(ROOT/engine['path'],engine['sha256']),sources,False)
 def envelope(prefix):return dict(document=docs[prefix+'_inputs'],publication=docs[prefix+'_publication'],readback=docs[prefix+'_readback'],references={r:refs[prefix+'_'+r] for r in ('inputs','publication','readback','reader')})
 args=dict(candidate_evidence=envelope('candidate'),original_eight_evidence=envelope('original'));guard(sources,parents)
 return dict(args=args,core=core,sources=sources,input_references=refs,parent_inventories=parents)
def run(*,execute=False):
 require(execute is True,'Explicit input preparation');c=load_inputs();require(not OUTPUT.exists(),'Create only no retry');resource();OUTPUT.mkdir(parents=True);written=[]
 try:
  written.append(save('started.json',dict(schema='MULTIDECISION_ORIGINAL_EIGHT_INPUTS_STARTED_V1',input_references=c['input_references'],source_hashes=c['sources'],**FLAGS)))
  guard(c['sources'],c['parent_inventories']);value=c['core'].prepare_incumbent_account_inputs(**c['args'])
  raw=save('inputs.json',dict(schema='MULTIDECISION_ORIGINAL_EIGHT_INPUTS_DOCUMENT_V1',inputs=value,input_references=c['input_references'],source_hashes=c['sources'],independent_readback_status='PENDING',parent_started_dispatch_authority_verified=False,**FLAGS),True);written.append(raw)
  require(value['schema']=='MULTIDECISION_ORIGINAL_EIGHT_CONTROL_INPUTS_V1' and enc([value['coordinate_count'],value['lane_count'],value['track_count']])==enc([48,8,16]),'Complete result domains')
  for k in c['core'].FLAGS:require(value[k] is False,'No authority escalation')
  guard(c['sources'],c['parent_inventories']);written.append(save('publication.json',dict(schema='MULTIDECISION_ORIGINAL_EIGHT_INPUTS_PUBLICATION_V1',status='PUBLISHED_CONTROL_INPUTS_PENDING_INDEPENDENT_READBACK_NOT_ACCOUNTS',inputs_reference=raw,started_reference=written[0],input_references=c['input_references'],source_hashes=c['sources'],**FLAGS)))
  guard(c['sources'],c['parent_inventories']);inventory(OUTPUT,['started.json','inputs.json','publication.json'])
  for r in written:require(hashfile(r['path'])==r['sha256'],'Final output drift')
  return raw
 except BaseException as e:
  if not (OUTPUT/'failure.json').exists():save('failure.json',dict(status='FAILED_NO_RETRY',saved_references=written,error=dict(type=type(e).__name__,message=str(e),traceback=traceback.format_exc()),**FLAGS),True)
  raise

if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');print(json.dumps(run(execute=p.parse_args().execute)))
