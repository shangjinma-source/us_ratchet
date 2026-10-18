"""Independent source projection and complete four-lane ordering; never calls selector/adapter."""
from pathlib import Path
from copy import deepcopy
import hashlib,json,os,re,shutil,types,sys
SOURCE=Path(__file__).resolve();ROOT=SOURCE.parents[1];LOADED_SHA=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
PARENT=ROOT/'data/cache/research/registered_scoring_selection_20261003_v1'
OUTPUT=ROOT/'data/cache/research/registered_scoring_selection_independent_readback_20261003_v1'
INDEX_SHA='cf5a8fc546dcc2454bf986c31dacfff60df109adecb1b0e4b4c681bd59fce6b4'
PUBLICATION_SHA='79b288a81f2431865123672b3cc6a6968cafa2cc10c72c987332e7fc65beae58'
PRODUCER=ROOT/'scripts/ndx_registered_scoring_selection_20261003.py'
PRODUCER_SHA='ae983b808273d29a4526261240264063ea0748c17827c554898e38adfdcb57dd'
RANK_INSPECTOR=ROOT/'backtest/ndx_full_ndx_selection_inspection_research.py'
RANK_INSPECTOR_SHA='cb155f02e99fb1a3750778c70caa88e81ee2eaade62a9699640e553066534faf'
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
def resource_gate(score_bytes=0,write_bytes=0,preserved_output_bytes=0):
    require(type(score_bytes) is int and 0<=score_bytes<=MAX_SCORE_BYTES,'Explicit complete score-byte engineering limit; no topN')
    require(type(preserved_output_bytes) is int and preserved_output_bytes>=0,'Exact complete preserved-output bytes')
    # Same conservative 32x expansion as B, additionally budgeting both saved
    # full-output JSON objects; an engineering allowance, not a peak-RSS proof.
    require(available_memory()>=5*1024**3+(score_bytes+preserved_output_bytes)*32,'Insufficient memory for full preserved-score adapter and saved outputs; no reduced domain')
    p=OUTPUT.parent
    while not p.exists():p=p.parent
    require(shutil.disk_usage(p).free>=5*1024**3+write_bytes,'Insufficient output space')
def save(path,value,emergency=False):
    b=enc(value)
    if not emergency:resource_gate(write_bytes=len(b))
    with path.open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
    require(path.read_bytes()==b,'Saved output changed');return ref(path,sha(b))

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
    s={};take(ref(PRODUCER,PRODUCER_SHA),s);d={};refs={}
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
    for p,h in CODES.values():take(ref(p,h),s)
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


def locate_original_scores(d,refs,reports):
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


def source_sets(d,reports):
    require({p.name for p in AUDIT_ROOT.iterdir()}=={'started.json','independent_readback.json',*(f'shard_{i:04d}.json' for i in range(306))},'Exact complete audit namespace')
    requestdir=Path(BOUND['request'][0]).parent
    require({p.name for p in requestdir.iterdir()}=={'started.json','result.json'},'Exact successful request')
    for _,a in reports:
        directory=Path(a['journal_reference']['path']).parent
        require({p.name for p in directory.iterdir()}=={'started.json','journal.jsonl','result.json'},'Exact accepted shard, no later failure/alien output')


def inspect_projected_inputs(prepared,budget,refs,projections):
    """Independent field projection checks; source scores are never recomputed."""
    require(prepared['schema']=='REGISTERED_SCORING_SELECTOR_INPUTS_V1','Saved preparation schema')
    require(prepared['content_sha256']==sha(enc({k:v for k,v in prepared.items() if k!='content_sha256'})),'Saved input digest')
    for k in ('source_bytes_authenticated','score_reference_bytes_authenticated','selector_called','score_computed','fit_performed','account_executed','point_in_time_verified','complete_ndx_universe_verified','outer_lane_prior_resolved','selected_weights_are_execution_targets','mode_selected_using_results','formal_benchmark_passed','promotion_allowed'):require(prepared[k] is False,'Original preparation authority')
    exact(prepared['budget_reference'],refs['budget'],'Input budget binding');exact(prepared['budget_audit_reference'],refs['budget_audit'],'Original budget audit')
    u=budget['full_universe_preserved'];by={r['security_id']:r for r in u};require(len(u)==len(by)==77 and len({r['issuer_id'] for r in u})==76,'Full77/76')
    multiplicities={}
    for v in u:multiplicities[v['issuer_id']]=multiplicities.get(v['issuer_id'],0)+1
    polynomial=[1]
    for n in multiplicities.values():
        polynomial.append(0)
        for k in range(len(polynomial)-1,0,-1):polynomial[k]+=n*polynomial[k-1]
    cards=[dict(holding_count=k,combination_count=n) for k,n in enumerate(polynomial) if k]
    full=sum(polynomial[1:]);registration=dict(schema='FULL_NDX_MULTIDECISION_SELECTION_REGISTRATION_V1',policy_id='FULL_NDX_FOUR_LANE_RESEARCH_SELECTOR_JOB_ID_TIE_V1',registration_reference=refs['policy'],scope_reference=budget['registration_reference_preserved'],universe_scope='ALL_CONDITIONAL_NDX_MEMBERS_ALL_INDUSTRIES',sector_filter_applied=False,decision_cutoffs=[r['cutoff'] for r in budget['rows']],fx_modes=['STRICT_SAME_SESSION_FX','BACKWARD_LATEST_VALID_FX'],universe=u,all_k_denominators=cards,coordinates=[])
    cursor=0;record_index=0;blocked_count=0
    require(len(budget['rows'])==len(budget['decision_inputs_preserved'])==6,'All decisions')
    for j,(row,d) in enumerate(zip(budget['rows'],budget['decision_inputs_preserved'])):
        days=d['scoring_price_dates'];cutoff=row['cutoff'];qual={q['security_id']:q for q in d['qualifications']}
        semantics=sha(enc(dict(policy_reference=budget['registration_reference_preserved'],scoring_policy=budget['registration_preserved']['scoring'],fitter_source_reference=d['fitter_source_reference'])))
        exclusions=[]
        for n,e in enumerate(row['excluded_securities']):
            for reason in e['reasons']:exclusions.append(dict(reason_code=reason,security_ids=[e['security_id']],holding_counts=[],evidence_reference=dict(refs['budget'],json_pointer=f'/plan/rows/{j}/excluded_securities/{n}')))
        for n,card in enumerate(row['domain_coverage']):
            if card['necessary_bound_certificates']:exclusions.append(dict(reason_code='REGISTERED_NECESSARY_BOUND',security_ids=[],holding_counts=[card['k']],evidence_reference=dict(refs['budget'],json_pointer=f'/plan/rows/{j}/domain_coverage/{n}')))
        for mi,mode in enumerate(row['mode_plans']):
            source=d['mode_sources'][mi];blocked=not source['complete_thirteen_windows'];tasks=mode['tasks']
            coordinate=dict(cutoff=cutoff,decision_date=cutoff,fx_mode=source['mode'],expected_job_ids=[t['job_id'] for t in tasks],source_status='SOURCE_BLOCKED' if blocked else 'READY_FOR_SCORING',source_blockers=[dict(reason_code='TARGET_FULL13_SOURCE_BLOCKED',evidence_reference=source['reference'])] if blocked else [],training_semantics_sha256=semantics,budget_reference=refs['budget'],scoring_price_dates=days,budget_coverage=dict(full_combination_count=full,full_three_spec_task_denominator=full*3,registered_task_count=len(tasks),unscored_full_domain_task_count=full*3-len(tasks),pre_registered_exclusions=exclusions),full_domain_coverage_preserved=row['domain_coverage'],qualification_rows_preserved=d['qualifications'])
            registration['coordinates'].append(coordinate)
            for ti,job in enumerate(tasks):
                require(cursor<len(projections),'Missing source task');p=projections[cursor];require(job['job_id']==p['job_id'],'Original logical order')
                expected_ledger=dict(logical_ordinal=cursor,decision_index=j,mode_index=mi,task_index=ti,job_id=job['job_id'],outcome=p['outcome'],source_kind=p['source_kind'],evidence_preserved={k:v for k,v in p.items() if k not in ('score','inspection')})
                exact(prepared['logical_task_ledger'][cursor],expected_ledger,'Original task evidence/byte locator preserved');cursor+=1
                if blocked:
                    require(p['outcome']=='SOURCE_BLOCKED' and p['source_kind']=='REGISTERED_SOURCE_BLOCKED' and all(p[k] is None for k in ('score','inspection','score_reference','inspection_reference')),'Blocked remains unscored');blocked_count+=1;continue
                require(p['outcome']=='SCORED_PENDING_INDEPENDENT_READBACK' and p['error'] is None,'No incomplete or failed ranking')
                score=p['score'];audit=p['inspection'];require(audit['status']=='PASS' and audit['job_id']==job['job_id'],'Source arithmetic audit association')
                sids=job['identity']['security_ids'];task=dict(job_id=job['job_id'],cutoff=cutoff,decision_date=cutoff,fx_mode=source['mode'],security_ids=sorted(sids),holding_count=len(sids),tickers=';'.join(sorted(by[s]['ticker'] for s in sids)),weight_spec=job['identity']['weight_spec'])
                windows=[];risk=True;require(len(score['windows'])==13,'Original complete13')
                for i,w in enumerate(score['windows']):
                    checks=w['risk_checks'];require(set(checks)=={'MAX_SINGLE_WEIGHT','MIN_SINGLE_WEIGHT','SECURITY_TOP3_WEIGHT','MINIMUM_EFFECTIVE_N','RISK_CHAIN_TOP1_WEIGHT'} and all(type(v) is bool for v in checks.values()),'Preserved five original risk booleans');risk=risk and all(checks.values())
                    left=i*21;windows.append(dict(window_index=i,status='COMPLETE',fit_return_count=126,evaluation_return_count=126,fit_price_predecessor=days[left],evaluation_price_predecessor=days[left+126],fit_first_return_end=days[left+1],fit_last_return_end=days[left+126],evaluation_first_return_end=days[left+127],evaluation_last_return_end=days[left+252]))
                require(score['fractional_risk_passed'] is risk,'Original risk summary')
                for sid in sids:require(all(qual[sid][k] is True for k in ('history_13_complete','mdv_available','liquidity_passed','conditional_member_scope_passed')),'Source qualification gates, not actual PIT')
                values={k:task[k] for k in ('security_ids','holding_count','tickers','weight_spec')};values.update(score['metrics'])
                expected_record=dict(task=task,status='EVALUATED',result=values,training_semantics_sha256=semantics,evidence_reference=p['evidence_reference'],eligibility=dict(fractional_risk_passed=risk,liquidity_passed=True,conditional_member_scope_passed=True),scoring_windows=windows,original_fitted_security_order=sids,score_reference=p['score_reference'],inspection_reference=p['inspection_reference'],saved_score_preserved=score,independent_inspection_preserved=audit)
                exact(prepared['records'][record_index],expected_record,'Every saved metric, coordinate, qualification, source and original score exact');record_index+=1
    exact(prepared['registration'],registration,'Full independent registration reconstruction')
    require(cursor==len(projections)==len(prepared['logical_task_ledger']) and record_index==len(prepared['records']),'No missing or extra task')
    for k,n in (('logical_task_count',cursor),('source_blocked_task_count',blocked_count),('evaluated_task_count',record_index),('nonrankable_task_count',0)):require(type(prepared[k]) is int and prepared[k]==n,'Exact projection denominator')
    return dict(logical_task_count=cursor,source_blocked_task_count=blocked_count,evaluated_task_count=record_index,coordinate_count=12,original_scores_recomputed=False,source_values_projected_exact=True)


def inspect_output_envelopes(documents,refs,input_refs,producer_sources):
    start=documents['started'];index=documents['index'];pub=documents['publication'];rawin=documents['raw_inputs'];rawsel=documents['raw_selection']
    require(start['schema']=='REGISTERED_SCORING_SELECTION_STARTED_V1','Start schema')
    require(index['schema']=='REGISTERED_SCORING_SELECTION_INDEX_V1' and index['status']=='CONDITIONAL_SELECTION_PENDING_INDEPENDENT_READBACK','Index role')
    require(pub['schema']=='REGISTERED_SCORING_SELECTION_PUBLICATION_V1' and pub['status']=='PUBLISHED_CONDITIONAL_SELECTION_ONLY','Published conditional result')
    for role,d in documents.items():
        exact(d['source_hashes'],producer_sources,'Independently constructed producer closure')
        for k in FLAGS:require(d[k] is False,'No advertised authority')
        if role!='publication':exact(d['input_references'],input_refs,'All original source role refs')
    for key,role in (('started_reference','started'),('selector_inputs_reference','raw_inputs'),('selection_reference','raw_selection')):exact(index[key],refs[role],'Index exact output binding')
    for key,role in (('index_reference','index'),('raw_inputs_reference','raw_inputs'),('raw_selection_reference','raw_selection'),('started_reference','started')):exact(pub[key],refs[role],'Publication exact output binding')
    for role,schema in (('raw_inputs','REGISTERED_SCORING_SELECTOR_INPUTS_RAW_V1'),('raw_selection','REGISTERED_SCORING_SELECTION_RAW_V1')):
        require(documents[role]['schema']==schema and documents[role]['status']=='RETURNED_PENDING_VALIDATION_NOT_RANKING_AUTHORITY' and type(documents[role]['result']) is dict,'Original successful raw return')
    for key,n in (('logical_task_count',19584),('source_blocked_task_count',9792),('evaluated_task_count',9792),('coordinate_count',12),('lane_count_per_coordinate',4)):require(type(index[key]) is int and index[key]==n,'Whole index denominator')
    for key,n in (('registered_logical_task_count',19584),('registered_executable_task_count',9792),('original_strict_source_blocked_task_count',9792)):require(type(start[key]) is int and start[key]==n,'Start whole domain')
    require(index['cutoff_refit_required'] is True and index['selector_called'] is True and index['arithmetic_or_optimizer_rerun'] is False,'Selection stage scope')
    for k,v in (('selector_inputs_json_pointer','/result'),('selection_json_pointer','/result'),('full_ledger_pointer','/result/logical_task_ledger'),('full_records_pointer','/result/records')):require(index[k]==v,'Actual full output pointer')


def readback(*,execute=False):
    require(type(execute) is bool,'Exact execute flag')
    if not execute:return dict(status='NOT_EXECUTED')
    require(all(type(h) is str and re.fullmatch('[a-f0-9]{64}',h) is not None for h in (INDEX_SHA,PUBLICATION_SHA,PRODUCER_SHA)),'Future selection output/code anchors pending')
    require(all(type(p) is str and type(h) is str and re.fullmatch('[a-f0-9]{64}',h) is not None for p,h in BOUND.values()),'Final parent source anchors pending')
    require(not OUTPUT.exists(),'Existing independent namespace; no retry')
    names={'started.json','raw_inputs.json','raw_selection.json','index.json','publication.json'}
    require({p.name for p in PARENT.iterdir()}==names,'Successful exact five-file selection output')
    out_sources={};refs={'index':ref(PARENT/'index.json',INDEX_SHA),'publication':ref(PARENT/'publication.json',PUBLICATION_SHA)}
    documents={k:loads(take(r,out_sources)) for k,r in refs.items()};publication=documents['publication']
    for role in ('started','raw_inputs','raw_selection'):
        r=publication[role+'_reference'];valid(r);require(Path(r['path'])==PARENT/(role+'.json'),'Bound actual output path');refs[role]=r
    documents['started']=loads(take(refs['started'],out_sources))
    # Complete 306-report locator total and its original resource gate precede
    # reading/parsing either large raw output. Never reduce the score domain.
    d,input_refs,producer_sources,reports,size=load_metadata();source_sets(d,reports)
    raw_sizes={role:Path(refs[role]['path']).stat().st_size for role in ('raw_inputs','raw_selection')}
    resource_gate(score_bytes=size,preserved_output_bytes=sum(raw_sizes.values()))
    for role,expected_size in raw_sizes.items():
        r=refs[role];p=Path(r['path']);require(not (p.parent/'failure.json').exists(),'Failed source namespace')
        with p.open('rb') as stream:raw=stream.read(expected_size+1)
        require(len(raw)==expected_size and sha(raw)==r['sha256'],'Size-budgeted authenticated output bytes');merge(out_sources,r)
        documents[role]=loads(raw)
    del raw
    inspect_output_envelopes(documents,refs,input_refs,producer_sources)
    require(type(documents['started']['raw_score_record_bytes']) is int and documents['started']['raw_score_record_bytes']==size,'Actual observed score byte budget')
    sources=dict(producer_sources)
    for p,h in out_sources.items():merge(sources,ref(p,h))
    take(ref(SOURCE,LOADED_SHA),sources);b=take(ref(RANK_INSPECTOR,RANK_INSPECTOR_SHA),sources);core=types.ModuleType('_independent_rank');core.__file__=str(RANK_INSPECTOR);exec(compile(b,str(RANK_INSPECTOR),'exec'),core.__dict__)
    guard(sources);resource_gate();OUTPUT.mkdir(parents=True,exist_ok=False)
    try:
        started=save(OUTPUT/'started.json',dict(schema='REGISTERED_SCORING_SELECTION_READBACK_STARTED_V1',index_reference=refs['index'],publication_reference=refs['publication'],reader_sha256=LOADED_SHA,**FLAGS))
        originals=locate_original_scores(d,input_refs,reports)
        projection=inspect_projected_inputs(documents['raw_inputs']['result'],d['budget']['plan'],input_refs,originals);del originals
        inputs=documents['raw_inputs']['result'];detail=core.inspect_complete_selection(registration=inputs['registration'],records=inputs['records'],saved_selection=documents['raw_selection']['result'])
        require(detail['status']=='PASS','Independent four-lane ordering')
        report=save(OUTPUT/'independent_readback.json',dict(schema='REGISTERED_SCORING_SELECTION_INDEPENDENT_READBACK_V1',status='PASS',index_reference=refs['index'],publication_reference=refs['publication'],raw_inputs_reference=refs['raw_inputs'],raw_selection_reference=refs['raw_selection'],queue_audit_reference=input_refs['audit'],reader_sha256=LOADED_SHA,source_hashes=sources,projection_inspection=projection,ranking_inspection=detail,selector_called=False,adapter_called=False,upstream_score_arithmetic_reaudited=False,source_check_scope='HASHED_CONSUMED_BYTES_AND_FINAL_GUARD;NO_CONTINUOUS_MONITORING',**FLAGS))
        guard(sources);source_sets(d,reports)
        require({p.name for p in PARENT.iterdir()}==names,'Final exact source output set')
        for r in (started,report):require(filehash(r['path'])==r['sha256'],'Saved independent output drift')
        require({p.name for p in OUTPUT.iterdir()}=={'started.json','independent_readback.json'},'Exact independent output set');return report
    except Exception as e:
        save(OUTPUT/'failure.json',dict(status='FAILED_NOT_AUTHORIZED_NO_RETRY',error_type=type(e).__name__,error=str(e),**FLAGS),True);raise

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');print(json.dumps(readback(execute=parser.parse_args().execute)))
