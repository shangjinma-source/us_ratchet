"""Complete audited registered scores to frozen research selector; no numerical dispatch."""
from pathlib import Path
from copy import deepcopy
import hashlib,json,os,re,shutil,types,sys
SOURCE=Path(__file__).resolve();ROOT=SOURCE.parents[1];LOADED_SHA=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
OUTPUT=ROOT/'data/cache/research/registered_scoring_selection_20261003_v1'
QUEUE_ROOT=ROOT/'data/cache/research/registered_scoring_queue_worker_20261003_v1'
AUDIT_ROOT=ROOT/'data/cache/research/registered_scoring_queue_independent_readback_20261003_v2'
FIRST_ID='75ad5a6a98d6056d4f13962d31b43debc809d9d663f719639fd1ea5e80fd4598'
BOUND={
 'request':(str(ROOT/'data/cache/research/registered_scoring_queue_worker_20261003_v1/requests/99e7d62348d64ddbacd5b38307c2a050/result.json'),'4e162f87a383a90ddcf087c1342d06bd39df38d84e7d6dd85b748aa5668b7c5e'),
 'audit':(str(AUDIT_ROOT/'independent_readback.json'),'efd1a0c7e6475d28108d4537563c1590606e9f286b83f4046664ec5e1b922f23'),
 'reader':(str(ROOT/'scripts/ndx_registered_scoring_queue_independent_readback_v2_20261003.py'),'d640c9a479ae263d0ccfcb5b02b702eef114c06241775ac15bfd23c0d11056bc'),
 'budget':(str(ROOT/'data/cache/research/multidecision_scoring_budget_20261003_v1/plan.json'),'f99843ce3d28829f6c258e608a7e3c2ee8605e2432eaaa890299dc1f9edb6d04'),
 'budget_audit':(str(ROOT/'data/cache/research/multidecision_scoring_budget_independent_readback_20261003_v1/independent_readback.json'),'38446edc13b175845e364906a52c8117ebf5f53ed0abf13b459d55664178846c'),
 'policy':(str(ROOT/'research_contracts/multidecision_conditional_scoring_policy_20261003_v1.json'),'6cc7f67093ba996b7cad0c6e24acbc3691a457930103872b8105b6a44c38424f'),
 'first_audit':(str(ROOT/'data/cache/research/registered_scoring_first_task_independent_readback_20261003_v1'/FIRST_ID/'independent_readback.json'),'b227474d150f25eb742d0c549df01cd628cd88d5b38507e751651aebeac4ff7f'),
 'first_reader':(str(ROOT/'scripts/ndx_registered_scoring_first_task_independent_readback_20261003.py'),'0ae6d1ef179723133784f55cf92fde42c491b5392f4ab41f84546fef5d382f2d')}
CODES={
 'adapter':(str(ROOT/'backtest/ndx_registered_scoring_selector_adapter_research.py'),'2bfd07579f3741b05de909b3bc3a69e19a4199a56ce14eb04861c07c8db854d2'),
 'selector':(str(ROOT/'backtest/ndx_full_ndx_multidecision_selector_research.py'),'6c7f3d7c0cdae8b2bd24e663167160a322cf4d6e1be88d6a265a91d3bb1bc4dd')}
FLAGS=dict.fromkeys(('fit_performed','score_computed','account_executed','point_in_time_verified','complete_ndx_universe_verified','full_universe_search_verified','mode_selected_using_results','selected_weights_are_execution_targets','formal_benchmark_passed','promotion_allowed','execution_authorized','automatic_retry_allowed','continuous_source_monitoring_claimed'),False)
MAX_SCORE_BYTES=1024**3

def require(ok,msg):
    if not ok:raise ValueError(msg)
def enc(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(v):return hashlib.sha256(v).hexdigest()
def exact(a,b,msg):require(enc(a)==enc(b),msg)
def ref(path,h):return dict(path=str(Path(path).resolve()),sha256=h)
def valid(r):require(type(r) is dict and set(r)=={'path','sha256'} and type(r['path']) is str and Path(r['path']).is_absolute() and type(r['sha256']) is str and re.fullmatch('[a-f0-9]{64}',r['sha256']) is not None,'Exact immutable reference')
def merge(s,r):
    valid(r);require(r['path'] not in s or s[r['path']]==r['sha256'],'Source conflict');s[r['path']]=r['sha256']
def loads(b):
    def pairs(items):
        d={}
        for k,v in items:require(k not in d,'Duplicate JSON key');d[k]=v
        return d
    return json.loads(b,object_pairs_hook=pairs,parse_constant=lambda x:(_ for _ in ()).throw(ValueError('Nonfinite JSON')))
def take(r,s):
    valid(r);p=Path(r['path']);require(not (p.parent/'failure.json').exists(),'Failed source namespace');b=p.read_bytes();require(sha(b)==r['sha256'],'Same consumed bytes/hash');merge(s,r);return b
def filehash(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
def guard(s):
    require(filehash(SOURCE)==LOADED_SHA,'Loaded source changed')
    for p,h in s.items():require(not (Path(p).parent/'failure.json').exists() and filehash(p)==h,'Source drift '+p)
def available_memory():
    if os.name=='nt':
        import ctypes
        class Memory(ctypes.Structure):
            _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong)]+[(n,ctypes.c_ulonglong) for n in ('total','available','page_total','page_available','virtual_total','virtual_available','extended')]
        value=Memory();value.length=ctypes.sizeof(value);require(ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(value))!=0,'Memory state unavailable');return value.available
    return os.sysconf('SC_AVPHYS_PAGES')*os.sysconf('SC_PAGE_SIZE')
def resource_gate(score_bytes=0,write_bytes=0):
    require(type(score_bytes) is int and 0<=score_bytes<=MAX_SCORE_BYTES,'Explicit complete score-byte engineering limit; no topN')
    require(available_memory()>=5*1024**3+score_bytes*32,'Insufficient memory for full preserved-score adapter; no reduced domain')
    p=OUTPUT.parent
    while not p.exists():p=p.parent
    require(shutil.disk_usage(p).free>=5*1024**3+write_bytes,'Insufficient output space')
def save(path,value,emergency=False):
    b=enc(value)
    if not emergency:resource_gate(write_bytes=len(b))
    with path.open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
    require(path.read_bytes()==b,'Saved output changed');return ref(path,sha(b))
def compile_bound(role,s):
    p,h=CODES[role];b=take(ref(p,h),s);m=types.ModuleType('_selection_private_'+role);m.__file__=p;exec(compile(b,p,'exec'),m.__dict__);return m

def validate_parents(d,refs):
    a=d['audit'];r=d['request'];b=d['budget'];f=d['first_audit']
    require(a['schema']=='REGISTERED_SCORING_QUEUE_INDEPENDENT_READBACK_V1' and a['status']=='PASS' and a['full_queue_success_independently_verified'] is True,'Only final whole independently verified queue')
    exact(a['request_reference'],refs['request'],'Audit request anchor');require(a['reader_sha256']==refs['reader']['sha256'],'Final source reader version')
    for k in ('optimization_rerun','optimized_weights_independently_verified','recovery_certificates_recomputed','continuous_source_monitoring_claimed','point_in_time_verified','promotion_allowed'):require(a[k] is False,'No parent promotion')
    for k,n in (('logical_job_count',19584),('source_blocked_job_count',9792),('registered_executable_job_count',9792),('externally_audited_first_job_count',1),('new_numerical_job_denominator',9791),('independently_verified_new_success_count',9791),('terminal_failure_count',0),('unresolved_count',0),('undispatched_count',0)):
        require(type(a['counts'][k]) is int and a['counts'][k]==n,'Final complete denominator '+k)
    require(r['schema']=='REGISTERED_SCORING_REQUEST_RESULT_V1' and r['status']=='COMPLETE' and r['whole_queue_completed'] is True and len(r['completed_shard_references'])==306,'No partial ranking')
    exact(a['request_partition_preserved'],r,'Whole audited request preserved');require(len(a['shard_readback_references'])==306,'All306 shard audits')
    require(b['schema']=='MULTIDECISION_SCORING_BUDGET_DOCUMENT_V1','Budget document')
    ba=d['budget_audit'];require(ba['status']=='PASS','Budget prior readback');exact(ba['plan_reference'],refs['budget'],'Registered budget binding')
    exact(b['plan']['registration_reference_preserved'],refs['policy'],'Same frozen policy');exact(b['plan']['registration_preserved'],d['policy'],'Full frozen policy')
    require(f['schema']=='REGISTERED_SCORING_FIRST_TASK_INDEPENDENT_READBACK_V1' and f['status']=='PASS' and f['job_id']==FIRST_ID and f['reader_sha256']==refs['first_reader']['sha256'],'Same accepted first job')
    exact(a['first_independent_inspection'],f['inspection'],'First is same inspection structure, not arithmetic exemption')
    expected=dict(f['evidence_references'],independent_readback=refs['first_audit']);exact(a['first_external_reference'],expected,'First original six evidence sources')
    for role in ('budget','budget_audit','policy','first_audit','first_reader'):
        rr=refs[role];require(a['common_source_hashes'][rr['path']]==rr['sha256'],'Audit includes actual fixed role '+role)


def load_metadata():
    require(all(type(p) is str and type(h) is str and re.fullmatch('[a-f0-9]{64}',h) is not None for p,h in BOUND.values()),'Final external source anchors pending')
    s={str(SOURCE):LOADED_SHA};d={};refs={}
    for role,(p,h) in BOUND.items():
        refs[role]=ref(p,h);raw=take(refs[role],s)
        if role not in ('reader','first_reader'):d[role]=loads(raw)
    validate_parents(d,refs)
    for name in ('common_source_hashes','attempt_source_hashes'):
        for p,h in d['audit'][name].items():merge(s,ref(p,h))
    # Known reader authenticates this full map; this wrapper verifies every byte,
    # using the journal stream itself for its first hash instead of duplicate IO.
    reports=[];size=0
    for i,r in enumerate(d['audit']['shard_readback_references']):
        require(Path(r['path'])==AUDIT_ROOT/f'shard_{i:04d}.json','Original complete shard report path')
        a=loads(take(r,s));require(a['schema']=='REGISTERED_SCORING_SHARD_INDEPENDENT_READBACK_V1' and a['status']=='PASS_EVIDENCE_CLASSIFICATION' and a['result_status']=='COMPLETE','Successful shard audit')
        require(type(a['shard_index']) is int and a['shard_index']==i and a['reader_sha256']==refs['reader']['sha256'],'Stable shard reader/order')
        exact(a['result_reference'],d['request']['completed_shard_references'][i],'Original request/result/audit order')
        require(a['verified_new_success_count']==(31 if i==0 else 32) and type(a['verified_new_success_count']) is int and a['terminal_failure_count']==0 and type(a['terminal_failure_count']) is int,'Complete audited new-job count')
        require(len(a['job_inspections'])==a['verified_new_success_count'] and not a['unresolved_task_ids'] and not a['undispatched_task_ids'],'No hidden incomplete jobs')
        for p,h in a['source_hashes'].items():require(d['audit']['attempt_source_hashes'][p]==h,'Final audit covers shard source')
        require(Path(a['journal_reference']['path'])==QUEUE_ROOT/'shards'/f'{i:04d}'/'journal.jsonl','Fixed original journal')
        for row in a['job_inspections']:
            locator=row['score_reference']['record_locator'];size+=locator['byte_stop']-locator['byte_start']
        reports.append((r,a))
    first_score=d['first_audit']['evidence_references']['raw_score'];size+=Path(first_score['path']).stat().st_size
    resource_gate(size)
    journals={a['journal_reference']['path'] for _,a in reports};guard({p:h for p,h in s.items() if p not in journals})
    return d,refs,s,reports,size


def read_scored_records(stream,journal_reference,expected):
    """Yield original score bodies only; full stream hash validated at exhaustion."""
    valid(journal_reference);h=hashlib.sha256();offset=0;cursor=0
    require(type(expected) is list,'Ordered raw score locators')
    for _,loc in expected:
        require(set(loc)=={'sequence','byte_start','byte_stop','record_sha256','stage'} and loc['stage']=='RAW_SCORE','Exact real RAW_SCORE byte locator')
        for k in ('sequence','byte_start','byte_stop'):require(type(loc[k]) is int and loc[k]>=0,'Exact locator integer')
        require(loc['byte_stop']>loc['byte_start'],'Nonempty raw record')
    require([loc['byte_start'] for _,loc in expected]==sorted({loc['byte_start'] for _,loc in expected}),'No duplicate/swapped score location')
    for sequence,line in enumerate(stream):
        require(type(line) is bytes and line.endswith(b'\n'),'Complete binary journal lines');h.update(line);stop=offset+len(line)
        if cursor<len(expected) and offset==expected[cursor][1]['byte_start']:
            jid,loc=expected[cursor];require(stop==loc['byte_stop'] and sequence==loc['sequence'],'Exact record boundaries')
            row=loads(line);require(enc(row)+b'\n'==line,'Canonical original record')
            require(row['record_sha256']==loc['record_sha256']==sha(enc({k:v for k,v in row.items() if k!='record_sha256'})),'Original record content hash')
            require(row['task_id']==jid and row['stage']=='RAW_SCORE','Exact job score record')
            payload=row['payload'];require(payload['returned'] is True and payload['call_invoked'] is True and payload['returned_call_count']==1 and type(payload['returned_call_count']) is int and payload['error'] is None and payload['result_preserved_as_json'] is True and type(payload['result']) is dict,'Actual saved successful score body')
            cursor+=1;yield jid,payload['result']
        elif cursor<len(expected):require(stop<=expected[cursor][1]['byte_start'],'Missing or shifted record')
        offset=stop
    require(cursor==len(expected) and h.hexdigest()==journal_reference['sha256'],'Full journal EOF and external SHA')


def project_scores(d,refs,reports):
    first=d['first_audit'];r=first['evidence_references']['raw_score'];score=loads(take(r,{}))
    require(score['job_id']==FIRST_ID and score['schema']=='REGISTERED_SCORING_RAW_SCORE_V1' and score['returned'] is True and score['error'] is None and type(score['result']) is dict,'First original raw score')
    successful={FIRST_ID:dict(job_id=FIRST_ID,outcome='SCORED_PENDING_INDEPENDENT_READBACK',source_kind='FIRST_EXTERNAL',score=score['result'],inspection=first['inspection'],score_reference=dict(r,json_pointer='/result'),inspection_reference=dict(refs['first_audit'],json_pointer='/inspection'),evidence_reference=dict(refs['first_audit'],json_pointer='/inspection'),error=None)}
    for reportref,a in reports:
        expected=[];by={}
        for i,row in enumerate(a['job_inspections']):
            require(row['job_id'] not in by and row['job_id'] not in successful,'No duplicate score task');require(row['outcome']=='SCORED_PENDING_INDEPENDENT_READBACK' and row['source_kind']=='JOURNAL','Only full numeric success')
            exact(row['score_reference']['journal_reference'],a['journal_reference'],'Audited journal role');require(row['score_reference']['result_field']=='payload.result','Original score field')
            by[row['job_id']]=(i,row);expected.append((row['job_id'],row['score_reference']['record_locator']))
        with Path(a['journal_reference']['path']).open('rb') as stream:
            for jid,score in read_scored_records(stream,a['journal_reference'],expected):
                i,row=by[jid];successful[jid]=dict(job_id=jid,outcome=row['outcome'],source_kind='JOURNAL',score=score,inspection=row['inspection'],score_reference=row['score_reference'],inspection_reference=dict(reportref,json_pointer=f'/job_inspections/{i}/inspection'),evidence_reference=dict(reportref,json_pointer=f'/job_inspections/{i}'),error=None)
    result=[]
    for j,row in enumerate(d['budget']['plan']['rows']):
        for mi,mode in enumerate(row['mode_plans']):
            for ti,job in enumerate(mode['tasks']):
                if job['status']=='SOURCE_BLOCKED':result.append(dict(job_id=job['job_id'],outcome='SOURCE_BLOCKED',source_kind='REGISTERED_SOURCE_BLOCKED',score=None,inspection=None,score_reference=None,inspection_reference=None,evidence_reference=dict(refs['budget'],json_pointer=f'/plan/rows/{j}/mode_plans/{mi}/tasks/{ti}'),error=None))
                else:
                    require(job['job_id'] in successful,'Every executable job independently supplied');result.append(successful.pop(job['job_id']))
    require(not successful and len(result)==19584,'No extra or missing logical task')
    return result

def validate_adapter(out):
    require(type(out) is dict and out['schema']=='REGISTERED_SCORING_SELECTOR_INPUTS_V1','Returned adapter object')
    require(out['content_sha256']==sha(enc({k:v for k,v in out.items() if k!='content_sha256'})),'Complete adapter original digest')
    for k,n in (('logical_task_count',19584),('source_blocked_task_count',9792),('evaluated_task_count',9792),('nonrankable_task_count',0)):
        require(type(out[k]) is int and out[k]==n,'Complete adapter denominator')
    require(len(out['logical_task_ledger'])==19584 and len(out['records'])==9792 and len(out['registration']['coordinates'])==12,'All logical/record/coordinate arrays')
    for k in ('source_bytes_authenticated','score_reference_bytes_authenticated','selector_called','score_computed','fit_performed','account_executed','point_in_time_verified','complete_ndx_universe_verified','outer_lane_prior_resolved','selected_weights_are_execution_targets','mode_selected_using_results','formal_benchmark_passed','promotion_allowed'):require(out[k] is False,'Original adapter scope')

def validate_selection(out,prepared):
    require(type(out) is dict and out['schema']=='FULL_NDX_MULTIDECISION_FOUR_LANE_SELECTION_V1','Returned selector object')
    require(out['content_sha256']==sha(enc({k:v for k,v in out.items() if k!='content_sha256'})),'Complete selection digest')
    exact(out['registration_preserved'],prepared['registration'],'Full coordinate registration preserved');exact(out['records_preserved'],prepared['records'],'All source scores preserved')
    require(out['global_input_errors']==[] and len(out['rows'])==12,'Complete valid selector input')
    for i,row in enumerate(out['rows']):
        exact(row['coordinate_preserved'],prepared['registration']['coordinates'][i],'Exact coordinate scope');require(row['input_errors']==[] and len(row['choices'])==4,'Four lanes, no implicit invalid winner')
        require(type(row['expected_task_count']) is int and row['expected_task_count']==1632,'Original mode budget')
        if i%2==0:require(all(c['status']=='SOURCE_BLOCKED' and c['selected'] is None for c in row['choices']),'Strict blocked never replaced')
        else:require(all(c['status'] in ('NO_ELIGIBLE_CANDIDATE','SELECTED_REQUIRES_NEW_CUTOFF_REFIT') for c in row['choices']),'Only conditional candidate selection')
    for k in ('source_bytes_authenticated','eligibility_source_authenticity_verified','point_in_time_verified','complete_ndx_universe_verified','full_universe_search_verified','sector_filter_applied','mode_selected_using_results','saved_weights_are_execution_targets','prior_resolved','numerical_task_ids_generated','implicit_carry_forward','fit_performed','account_executed','promotion_allowed','execution_authorized','formal_benchmark_passed'):require(out[k] is False,'No selection authority escalation')
    require(out['cutoff_refit_required'] is True,'Selection does not produce execution targets')

def source_sets(d,reports):
    require({p.name for p in AUDIT_ROOT.iterdir()}=={'started.json','independent_readback.json',*(f'shard_{i:04d}.json' for i in range(306))},'Exact complete audit namespace')
    requestdir=Path(BOUND['request'][0]).parent
    require({p.name for p in requestdir.iterdir()}=={'started.json','result.json'},'Exact successful request')
    for _,a in reports:
        directory=Path(a['journal_reference']['path']).parent
        require({p.name for p in directory.iterdir()}=={'started.json','journal.jsonl','result.json'},'Exact accepted shard, no later failure/alien output')

def preserve_return(path,schema,result,refs,sources):
    envelope=dict(schema=schema,status='RETURNED_PENDING_VALIDATION_NOT_RANKING_AUTHORITY',result=result,input_references=refs,source_hashes=sources,**FLAGS)
    try:enc(envelope)
    except (TypeError,ValueError,OverflowError) as error:
        diagnostic=dict(schema=schema,status='UNSERIALIZABLE_RETURN_NOT_RANKING_AUTHORITY',result=None,error_type=type(error).__name__,error=str(error),input_references=refs,returned_type=type(result).__name__,**FLAGS)
        try:blob=repr(result).encode('utf-8')
        except Exception as representation_error:
            diagnostic.update(representation_unavailable=True,representation_error_type=type(representation_error).__name__,representation_error=str(representation_error))
        else:
            p=path.with_suffix('.repr.bin')
            with p.open('xb') as f:f.write(blob);f.flush();os.fsync(f.fileno())
            diagnostic.update(representation_unavailable=False,representation_reference=ref(p,sha(blob)))
        save(path,diagnostic,True)
        raise
    # Resource gates must not discard a return that has already happened.
    # Actual IO failure remains partial evidence and prohibits retry.
    return save(path,envelope,True)


def run(*,execute=False):
    require(type(execute) is bool,'Execute boolean')
    if not execute:return dict(status='NOT_EXECUTED')
    require(all(type(p) is str and type(h) is str and re.fullmatch('[a-f0-9]{64}',h) is not None for p,h in BOUND.values()),'Final external source anchors pending')
    require(not OUTPUT.exists(),'Existing immutable attempt; no retry')
    d,refs,sources,reports,score_bytes=load_metadata();source_sets(d,reports)
    adapter=compile_bound('adapter',sources);selector=compile_bound('selector',sources)
    resource_gate(score_bytes);OUTPUT.mkdir(parents=True,exist_ok=False)
    try:
        started=save(OUTPUT/'started.json',dict(schema='REGISTERED_SCORING_SELECTION_STARTED_V1',input_references=refs,source_hashes=sources,registered_logical_task_count=19584,registered_executable_task_count=9792,original_strict_source_blocked_task_count=9792,raw_score_record_bytes=score_bytes,resource_policy='COMPLETE_DOMAIN_ONLY;MAX1GIB_SCORE_BYTES;AVAILABLE_MEMORY_GE_5GIB_PLUS_32X_RECORD_BYTES',source_verification_scope='COMMON_SOURCES_AT_LOAD_AND_PUBLICATION;JOURNALS_STREAM_EOF_SHA_AND_PUBLICATION;NO_CONTINUOUS_MONITORING',**FLAGS))
        projections=project_scores(d,refs,reports)
        resource_gate()
        prepared=adapter.assemble_registered_selector_inputs(budget_plan=d['budget']['plan'],budget_reference=refs['budget'],budget_audit_reference=refs['budget_audit'],projections=projections,selection_registration_reference=refs['policy'])
        raw_inputs=preserve_return(OUTPUT/'raw_inputs.json','REGISTERED_SCORING_SELECTOR_INPUTS_RAW_V1',prepared,refs,sources)
        validate_adapter(prepared);del projections
        resource_gate()
        selected=selector.select_full_ndx_lanes(registration=prepared['registration'],records=prepared['records'])
        raw_selection=preserve_return(OUTPUT/'raw_selection.json','REGISTERED_SCORING_SELECTION_RAW_V1',selected,refs,sources)
        validate_selection(selected,prepared)
        index=save(OUTPUT/'index.json',dict(schema='REGISTERED_SCORING_SELECTION_INDEX_V1',status='CONDITIONAL_SELECTION_PENDING_INDEPENDENT_READBACK',input_references=refs,source_hashes=sources,started_reference=started,selector_inputs_reference=raw_inputs,selector_inputs_json_pointer='/result',selection_reference=raw_selection,selection_json_pointer='/result',logical_task_count=19584,source_blocked_task_count=9792,evaluated_task_count=9792,coordinate_count=12,lane_count_per_coordinate=4,cutoff_refit_required=True,selector_called=True,arithmetic_or_optimizer_rerun=False,full_ledger_pointer='/result/logical_task_ledger',full_records_pointer='/result/records',**FLAGS))
        guard(sources);source_sets(d,reports)
        publication=save(OUTPUT/'publication.json',dict(schema='REGISTERED_SCORING_SELECTION_PUBLICATION_V1',status='PUBLISHED_CONDITIONAL_SELECTION_ONLY',index_reference=index,raw_inputs_reference=raw_inputs,raw_selection_reference=raw_selection,started_reference=started,source_hashes=sources,**FLAGS))
        guard(sources);source_sets(d,reports)
        for r in (started,raw_inputs,raw_selection,index,publication):require(filehash(r['path'])==r['sha256'],'Final saved output drift')
        require({p.name for p in OUTPUT.iterdir()}=={'started.json','raw_inputs.json','raw_selection.json','index.json','publication.json'},'Exact successful namespace')
        return dict(index_reference=index,publication_reference=publication)
    except Exception as e:
        save(OUTPUT/'failure.json',dict(status='FAILED_NO_RETRY_NO_SELECTION_AUTHORITY',error_type=type(e).__name__,error=str(e),raw_returns_are_diagnostic_only=True,**FLAGS),True);raise

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');print(json.dumps(run(execute=p.parse_args().execute)))
