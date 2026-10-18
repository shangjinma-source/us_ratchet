"""Constant-size request accounting and canonical manifest hashchain.

One batch's independently checked runs are consumed and discarded. This pure
module authenticates byte structure and supplied classifications, not filesystem
sources or economics. No worker, evaluator, domain or account imports.
"""
import hashlib
import json

KINDS=('inspected_feasible','inspected_infeasible','evaluation_exception',
       'supplied_not_evaluated_technical','supplied_not_evaluated_budget',
       'validation_failure_returned','unresolved_dispatch_or_raw','undispatched')
NUMERIC=frozenset(KINDS[:2])
FLAGS=dict(source_bytes_authenticated=False,evaluator_called=False,automatic_retry_allowed=False,
           point_in_time_verified=False,promotion_allowed=False,full_ndx_certified=False)


def require(condition,message):
    if not condition:raise ValueError(message)


def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()
def digest(value):return hashlib.sha256(canonical(value)).hexdigest()
def exact(a,b,message):require(canonical(a)==canonical(b),message)


def integer(value):
    require(type(value)is int and value>=0,'Exact nonnegative integer');return value


def reference(value):
    require(type(value)is dict and set(value)=={'path','sha256'},'Exact external reference')
    require(type(value['path'])is str and value['path'] and value['path'].strip()==value['path'],'Explicit source path')
    sha=value['sha256'];require(type(sha)is str and len(sha)==64 and set(sha)<=set('0123456789abcdef'),'Original SHA256')


def context(*,registration_reference,preparation_reference,prepared_content_sha256,domain_counts,batch_size,request_index=0,prior_request_reference=None):
    reference(registration_reference);reference(preparation_reference)
    reference(dict(path='prepared-content',sha256=prepared_content_sha256))
    require(set(domain_counts)=={'scenario_count','pair_count','integer_count','financial_integer_count_before_issuer','structurally_excluded_integer_count'},'Complete original domain counts')
    for value in domain_counts.values():integer(value)
    require(domain_counts['scenario_count']>0 and domain_counts['financial_integer_count_before_issuer']==domain_counts['integer_count']+domain_counts['structurally_excluded_integer_count'],'Original complete domain partition')
    require(type(batch_size)is int and batch_size in(512,10000),'Supported engineering batch size')
    require(type(request_index)is int and request_index==0 and prior_request_reference is None,'Initial request only; no automatic resume')
    body=dict(schema='DOUBLE_REPLACEMENT_STREAM_REQUEST_CONTEXT_V1',registration_reference=registration_reference,preparation_reference=preparation_reference,prepared_content_sha256=prepared_content_sha256,domain_counts=domain_counts,batch_size=batch_size,request_index=request_index,prior_request_reference=None,**FLAGS)
    # Freeze caller-owned mappings by a canonical round trip.
    body=json.loads(canonical(body));return dict(document=body,content_sha256=digest(body))


def checked_context(value):
    require(type(value)is dict and set(value)=={'document','content_sha256'},'Context envelope')
    body=value['document'];require(digest(body)==value['content_sha256'],'Context content hash')
    rebuilt=context(**{key:body[key]for key in('registration_reference','preparation_reference','prepared_content_sha256','domain_counts','batch_size','request_index','prior_request_reference')})
    exact(value,rebuilt,'Exact context fields and authority')
    return json.loads(canonical(body))


def descriptor(context_value,index):
    body=checked_context(context_value);integer(index)
    start=index*body['batch_size'];total=body['domain_counts']['integer_count']
    require(start<total,'Batch in complete original domain')
    stop=min(start+body['batch_size'],total)
    return dict(batch_index=index,start=start,stop=stop,point_count=stop-start)


def summarize_runs(span,runs):
    """Consume an iterable; never retain runs or expand individual ordinals."""
    counts=dict.fromkeys(KINDS,0);cursor=span['start'];stopped=False;seen=False
    for run in runs:
        require(type(run)is dict and set(run)=={'start','stop','status'},'Exact independently checked run')
        start,stop=integer(run['start']),integer(run['stop']);kind=run['status']
        require(kind in KINDS[:-1],'A supplied batch cannot contain undispatched points')
        require(start==cursor<stop<=span['stop'],'No ordinal gap overlap or reorder')
        require(not stopped or kind not in NUMERIC,'No numeric result after technical stop')
        stopped=stopped or kind not in NUMERIC;counts[kind]+=stop-start;cursor=stop;seen=True
    require(seen and cursor==span['stop'],'Full original batch including tail')
    return dict(counts=counts,terminal_status='TECHNICAL_STOP'if stopped else'COMPLETE_NUMERIC_BATCH')


def manifest_record(*,context_value,sequence,previous_record_sha256,batch_reference,verified_runs):
    integer(sequence);reference(batch_reference)
    if sequence==0:require(previous_record_sha256 is None,'First manifest record has no predecessor')
    else:reference(dict(path='previous-record',sha256=previous_record_sha256))
    span=descriptor(context_value,sequence)
    summary=summarize_runs(span,verified_runs)
    body=dict(schema='DOUBLE_REPLACEMENT_STREAM_BATCH_REFERENCE_V1',context_sha256=context_value['content_sha256'],sequence=sequence,previous_record_sha256=previous_record_sha256,descriptor=span,batch_result_reference=dict(batch_reference),**summary)
    return dict(record=body,record_sha256=digest(body))


def manifest_line(record):return canonical(record)+b'\n'


class RequestAccumulator:
    """Independent streaming reconstruction; fixed state, no per-batch list.

    `verified_runs` must be produced by a separate reader from the authenticated
    batch RAW/inspection/result. Manifest-declared counts are never its substitute.
    consume() validates fully before mutating state, so rejected rows do not
    silently advance the chain. Rejected bytes must remain untouched by the IO
    wrapper; this class never grants append/retry permission.
    """
    def __init__(self,context_value,*,max_line_bytes=65536):
        self.body=checked_context(context_value);self.context_sha256=context_value['content_sha256']
        require(type(max_line_bytes)is int and max_line_bytes>0,'Explicit manifest record byte limit')
        self.max_line_bytes=max_line_bytes;self.sequence=0;self.end=0;self.previous=None
        self.counts=dict.fromkeys(KINDS,0);self.stopped=False;self.byte_count=0;self.hash=hashlib.sha256()

    def consume(self,line,*,batch_result_reference,verified_runs):
        require(not self.stopped,'No following batch after a technical stop')
        require(type(line)is bytes and 0<len(line)<=self.max_line_bytes and line.endswith(b'\n'),'Complete bounded original JSONL record')
        def pairs(items):
            value={}
            for key,item in items:require(key not in value,'Duplicate JSON key');value[key]=item
            return value
        def constant(token):raise ValueError('Nonfinite JSON token')
        row=json.loads(line,object_pairs_hook=pairs,parse_constant=constant)
        require(manifest_line(row)==line,'Canonical original manifest bytes')
        require(type(row)is dict and set(row)=={'record','record_sha256'},'Exact manifest envelope')
        record=row['record'];require(row['record_sha256']==digest(record),'Manifest record content hash')
        require(record['schema']=='DOUBLE_REPLACEMENT_STREAM_BATCH_REFERENCE_V1','Manifest record schema')
        require(type(record['sequence'])is int and record['sequence']==self.sequence,'Original contiguous batch sequence')
        require(record['context_sha256']==self.context_sha256 and record['previous_record_sha256']==self.previous,'Exact context and hashchain predecessor')
        size=self.body['batch_size'];total=self.body['domain_counts']['integer_count'];start=self.sequence*size
        require(start==self.end<total,'No skipped or out-of-domain batch')
        span=dict(batch_index=self.sequence,start=start,stop=min(start+size,total),point_count=min(size,total-start))
        exact(record['descriptor'],span,'Independently reconstructed full batch span')
        reference(batch_result_reference);exact(record['batch_result_reference'],batch_result_reference,'Authenticated physical batch result reference')
        local=summarize_runs(span,verified_runs)
        expected=dict(schema='DOUBLE_REPLACEMENT_STREAM_BATCH_REFERENCE_V1',context_sha256=self.context_sha256,sequence=self.sequence,previous_record_sha256=self.previous,descriptor=span,batch_result_reference=batch_result_reference,**local)
        exact(record,expected,'Manifest counts/status independently reconstructed from saved batch runs')
        for kind in KINDS:self.counts[kind]+=local['counts'][kind]
        self.sequence+=1;self.end=span['stop'];self.previous=row['record_sha256']
        self.stopped=local['terminal_status']=='TECHNICAL_STOP';self.byte_count+=len(line);self.hash.update(line)

    def finish(self,*,eof_observed,expected_manifest_sha256,expected_byte_count,expected_record_count,expected_last_record_sha256):
        require(eof_observed is True,'Physical manifest EOF must be observed by source reader')
        integer(expected_byte_count);integer(expected_record_count)
        reference(dict(path='manifest',sha256=expected_manifest_sha256))
        require(expected_manifest_sha256==self.hash.hexdigest()and expected_byte_count==self.byte_count and expected_record_count==self.sequence and expected_last_record_sha256==self.previous,'Exact external manifest bytes count chain and EOF')
        counts=dict(self.counts);total=self.body['domain_counts']['integer_count'];counts['undispatched']=total-self.end
        require(sum(counts.values())==total,'All original points in exactly one of eight partitions')
        full=counts['inspected_feasible']+counts['inspected_infeasible']==total
        return dict(schema='DOUBLE_REPLACEMENT_STREAM_REQUEST_INSPECTION_V1',context_sha256=self.context_sha256,manifest_sha256=self.hash.hexdigest(),manifest_byte_count=self.byte_count,manifest_record_count=self.sequence,last_record_sha256=self.previous,original_integer_count=total,next_undispatched_ordinal=self.end,counts=counts,full_domain_complete=full,status='FULL_NUMERIC_DOMAIN'if full else'TECHNICAL_STOP'if self.stopped else'PREFIX_ONLY',**FLAGS)
