"""Bounded engineering partitions and canonical single-member gzip, no evaluation.

All domain/registration fields are caller declarations. No source IO or authority.
"""
import gzip,hashlib,io,json

ENCODING=dict(json='UTF8_SORT_KEYS_COMPACT_ENSURE_ASCII_ALLOW_NAN_FALSE',gzip='GZIP_SINGLE_MEMBER',compresslevel=6,mtime=0,filename='')
STATUSES=('inspected_feasible','inspected_infeasible','evaluation_exception','supplied_not_evaluated_technical','supplied_not_evaluated_budget','validation_failure_returned','unresolved_dispatch_or_raw')
FLAGS=dict(source_bytes_authenticated=False,execution_authorized=False,evaluation_called=False,point_in_time_verified=False,promotion_allowed=False)
def require(ok,message):
 if not ok:raise ValueError(message)
def integer(v):require(type(v)is int and v>=0,'Exact nonnegative integer');return v
def encode(v):return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('utf-8')
def digest(v):return hashlib.sha256(encode(v)).hexdigest()
def source_ref(r):
 require(type(r)is dict and set(r)=={'path','sha256'}and type(r['path'])is str and r['path'],'Declared reference')
 require(type(r['sha256'])is str and len(r['sha256'])==64 and set(r['sha256'])<=set('0123456789abcdef'),'Declared SHA')
def build_plan(*,preparation_reference,prepared_content_sha256,scenario_count,pair_count,financial_integer_count_before_issuer,structurally_excluded_integer_count,integer_count,batch_size=512):
 source_ref(preparation_reference);source_ref(dict(path='content',sha256=prepared_content_sha256))
 require(type(batch_size)is int and batch_size in(512,10000),'Explicit supported engineering size')
 for n in (scenario_count,pair_count,financial_integer_count_before_issuer,structurally_excluded_integer_count,integer_count):integer(n)
 require(scenario_count>0 and financial_integer_count_before_issuer==structurally_excluded_integer_count+integer_count,'Original domain partition')
 document=dict(schema='DOUBLE_REPLACEMENT_COMPRESSED_BATCH_PLAN_V1',preparation_reference=dict(preparation_reference),prepared_content_sha256=prepared_content_sha256,scenario_count=scenario_count,pair_count=pair_count,financial_integer_count_before_issuer=financial_integer_count_before_issuer,structurally_excluded_integer_count=structurally_excluded_integer_count,integer_count=integer_count,batch_size=batch_size,batch_count=(integer_count+batch_size-1)//batch_size,**FLAGS)
 return dict(document=document,content_sha256=digest(document))
def checked(plan):
 require(type(plan)is dict and set(plan)=={'document','content_sha256'}and digest(plan['document'])==plan['content_sha256'],'Plan exact content')
 d=plan['document'];rebuilt=build_plan(**{k:d[k]for k in ('preparation_reference','prepared_content_sha256','scenario_count','pair_count','financial_integer_count_before_issuer','structurally_excluded_integer_count','integer_count','batch_size')})
 require(encode(plan)==encode(rebuilt),'Full declared plan structure');return d
def descriptor(plan,batch_index):
 d=checked(plan);integer(batch_index);require(batch_index<d['batch_count'],'Original batch index')
 start=batch_index*d['batch_size'];stop=min(start+d['batch_size'],d['integer_count'])
 return dict(schema='DOUBLE_REPLACEMENT_COMPRESSED_BATCH_DESCRIPTOR_V1',plan_sha256=plan['content_sha256'],batch_index=batch_index,start=start,stop=stop,point_count=stop-start)
def partition(plan,batch_outcomes):
 d=checked(plan);require(type(batch_outcomes)is list,'Complete provided batch prefix');counts=dict.fromkeys(STATUSES,0);end=0;stopped=False
 for i,item in enumerate(batch_outcomes):
  require(not stopped and type(item)is dict and set(item)=={'descriptor','point_runs'},'No later batch after technical stop')
  desc=descriptor(plan,i);require(encode(item['descriptor'])==encode(desc),'Exact ordered batch descriptor')
  runs=item['point_runs'];require(type(runs)is list and runs,'Explicit complete within-batch intervals');cursor=desc['start']
  for run in runs:
   require(type(run)is dict and set(run)=={'start','stop','status'}and run['status']in STATUSES,'Point interval role')
   require(not stopped or run['status']not in ('inspected_feasible','inspected_infeasible'),'No numeric results after within-batch stop')
   start,stop=integer(run['start']),integer(run['stop']);require(start==cursor<stop<=desc['stop'],'No gap overlap or missing point')
   counts[run['status']]+=stop-start;cursor=stop
   if run['status']not in ('inspected_feasible','inspected_infeasible'):stopped=True
  require(cursor==desc['stop'],'Complete supplied batch range');end=cursor
 counts['undispatched']=d['integer_count']-end;require(sum(counts.values())==d['integer_count'],'Full original integer domain')
 complete=counts['inspected_feasible']+counts['inspected_infeasible']==d['integer_count']
 return dict(schema='DOUBLE_REPLACEMENT_COMPRESSED_PARTITION_V1',plan_sha256=plan['content_sha256'],full_integer_count=d['integer_count'],counts=counts,undispatched_interval=dict(start=end,stop=d['integer_count']),full_domain_complete=complete,status='COMPLETE_INSPECTED_DOMAIN'if complete else'TECHNICAL_STOP'if stopped else'PREFIX_ONLY',counts_are_caller_supplied_not_authenticated=True,**FLAGS)

class HashSink:
 def __init__(self,sink,limit):self.sink=sink;self.limit=limit;self.count=0;self.hash=hashlib.sha256()
 def write(self,data):
  require(self.count+len(data)<=self.limit,'Compressed byte bound exceeded')
  written=self.sink.write(data);require(written==len(data),'Full compressed write')
  self.count+=len(data);self.hash.update(data);return written
 def flush(self):self.sink.flush()

def write_canonical_gzip(value,sink,*,max_compressed_bytes,max_uncompressed_bytes):
 for bound in(max_compressed_bytes,max_uncompressed_bytes):require(type(bound)is int and bound>0,'Explicit positive byte bound')
 packed=HashSink(sink,max_compressed_bytes);raw_hash=hashlib.sha256();raw_size=0
 with gzip.GzipFile(filename='',mode='wb',fileobj=packed,compresslevel=6,mtime=0)as zipped:
  for part in json.JSONEncoder(sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).iterencode(value):
   b=part.encode('utf-8');require(raw_size+len(b)<=max_uncompressed_bytes,'Uncompressed byte bound exceeded')
   zipped.write(b);raw_hash.update(b);raw_size+=len(b)
 packed.flush()
 return dict(schema='DOUBLE_REPLACEMENT_CANONICAL_GZIP_V1',encoding=dict(ENCODING),compressed_sha256=packed.hash.hexdigest(),compressed_byte_count=packed.count,uncompressed_sha256=raw_hash.hexdigest(),uncompressed_byte_count=raw_size)
def encode_canonical_gzip(value,*,max_compressed_bytes,max_uncompressed_bytes):
 buffer=io.BytesIO();metadata=write_canonical_gzip(value,buffer,max_compressed_bytes=max_compressed_bytes,max_uncompressed_bytes=max_uncompressed_bytes)
 return buffer.getvalue(),metadata
