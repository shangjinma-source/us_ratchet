"""Source-bound streaming selection; no evaluation, accounts, or audit replay.

Case receipts require the final publication. A streamed old source is not fully
authenticated until EOF; any earlier case files remain unconsumable if it fails.
"""
import argparse,hashlib,json,os,re,types,ctypes
from copy import deepcopy
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];SOURCE=Path(__file__).resolve();LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
OUTPUT=ROOT/'data/cache/research/cash_neighbor_combined_selection_20261008_v1'
PREP=ROOT/'data/cache/research/cash_topup_neighbor_preparation_20261003_v1'
BATCH=ROOT/'data/cache/research/cash_topup_neighbor_shard_evaluation_20261003_v1'
FIRST_ID='8b5320eb5ac613ddf6a69478f7e2360811688d1951b38c9e1d7b4ff34678febd'
FIRST=ROOT/'data/cache/research/cash_topup_neighbor_evaluation_20261003_v1'/FIRST_ID
BOUND={
 'preparation':(str(PREP/'preparation.json'),'04cf54101f56303cc656e60079f1434661845da6e13c6c7d23305f3e9f1dde2b'),
 'preparation_publication':(str(PREP/'publication.json'),'dbe1e731c02293dab4a5cca4f0fa7fbf84367cd201dbf90b9e703cab1fd86b53'),
 'preparation_audit':(str(ROOT/'data/cache/research/cash_topup_neighbor_preparation_independent_readback_20261003_v1/independent_readback.json'),'c29c98c5c48d61e2533c7a587291932eda3b5776d81a9d0288a75a6b7d891ce8'),
 'previous':(str(ROOT/'data/cache/research/old_holding_topup_research_20261002_v1/results.json'),'1192aa5876b8ea9e36c84ad33d88f5504df849e8612312f1886fad6b579351fb'),
 'previous_publication':(str(ROOT/'data/cache/research/old_holding_topup_research_20261002_v1/publication.json'),'ed4f230d5e74ac0fb2000149caab80825e48d36cf3d7cd98a5f0858abc0fbc16'),
 'previous_review':(str(ROOT/'DYNAMIC_OLD_HOLDING_TOPUP_INDEPENDENT_READBACK_20261002.md'),'40f02f234a2661b0c3e0bb0ed2e7456a038d664c2e0e631561826f7b1e57f9ec'),
 'paired':(str(ROOT/'data/cache/research/old_holding_topup_paired_account_20261002_v1/accounts.json'),'7d5df8f295657497f3919aa3458dff31f0c175a40f391eb6b37ac9e5b7512d6f'),
 'paired_publication':(str(ROOT/'data/cache/research/old_holding_topup_paired_account_20261002_v1/publication.json'),'fb9db1ac77fffec7ec90141a7b431b3f34fb4bac0329deb07245c85b22325e7e'),
 'full_audit':('E:\\Git\\us_ratchet\\data\\cache\\research\\cash_neighbor_combined_independent_readback_20261008_v2\\independent_readback.json', '0494bce00b44bc9f85f5c94c9195dc6c9767d80da324bbc28f4a50f63efc649d'),'full_audit_reader':('E:\\Git\\us_ratchet\\scripts\\ndx_cash_neighbor_combined_independent_readback_v2_20261008.py', '12c6dd67099199ff9aa641424150ca35dc2aa5803db0627fcc809e261253a3a7'),
 'first_started':(str(FIRST/'started.json'),'b2d44ac6acff14561f325fa1b3fa859895e253475bd924c764a7eeba6766ff3a'),
 'first_raw':(str(FIRST/'raw.json'),'9dd01e5f9fc167f462c00c7858b89de51d540b810c0a2b5a3d0b18fc5d04719c'),
 'first_postcheck':(str(FIRST/'postcheck.json'),'7df4aa5f7285af105bcca01cafa2e132c0c0a3b15eca8bc0d7ae9b78615a0a57'),
 'first_audit':(str(ROOT/'data/cache/research/cash_topup_neighbor_single_evaluation_independent_readback_20261003_v1'/FIRST_ID/'independent_readback.json'),'942edc8840a4ff81b273988663b8e3318e12453076ba4034ad1a26412368b411'),
 'selector':('E:\\Git\\us_ratchet\\backtest\\ndx_cash_neighbor_combined_stream_selection_research.py', '0406388e16dde6a270bf46600946fc4b7e962abcb4440fb3706e0e4eac33a308'),
 'original_policy':(str(ROOT/'backtest/ndx_cash_neighbor_selection_research.py'),'7c44c7fcedd298bb75eed2e9e94cd5587bff31cb0771947a7b540683e21a3879'),
 'json_stream':(str(ROOT/'backtest/ndx_research_json_rows_stream.py'),'b1a2ae63c68476dc952abf53bdd081e7f08cab3052ddc6fca5b61bd32091b86c')}
FLAGS=dict.fromkeys(('risk_recomputed','fees_recomputed','l1_recomputed','fit_performed','account_executed','orders_executed','point_in_time_verified','promotion_allowed','global_optimality_claimed','fresh_oos_claimed','old_audits_reexecuted','full_transitive_source_closure_reverified'),False)

def require(ok,msg):
    if not ok:raise ValueError(msg)
def enc(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(b):return hashlib.sha256(b).hexdigest()
def digest(v):return sha(enc(v))
def exact(a,b,msg):require(enc(a)==enc(b),msg)
def integer(v,n=None):require(type(v) is int and v>=0 and (n is None or v==n),'Exact nonnegative count');return v
def ref(p,h):return dict(path=str(p),sha256=h)
def validref(r):require(type(r) is dict and set(r)=={'path','sha256'} and type(r['path']) is str and r['path'].strip()==r['path'] and bool(r['path']) and type(r['sha256']) is str and re.fullmatch('[a-f0-9]{64}',r['sha256']),'Pending or invalid source anchor')
def loads(b):
    def pairs(xs):
        d={}
        for k,v in xs:require(k not in d,'Duplicate key');d[k]=v
        return d
    def bad(v):raise ValueError('Nonfinite JSON')
    return json.loads(b,object_pairs_hook=pairs,parse_constant=bad)
def merge(s,r):validref(r);require(r['path'] not in s or s[r['path']]==r['sha256'],'Source conflict');s[r['path']]=r['sha256']
def read(r,s):
    merge(s,r);b=Path(r['path']).read_bytes();require(sha(b)==r['sha256'],'Consumed source bytes');return b
def guard(s):
    require(sha(SOURCE.read_bytes())==LOADED,'Loaded wrapper drift')
    for p,h in s.items():require(sha(Path(p).read_bytes())==h,'Source drift '+p)
def save(p,v):
    b=enc(v)
    with p.open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
    require(p.read_bytes()==b,'Saved bytes');return ref(p,sha(b))
def private_module(blob,path):
    module=types.ModuleType('_private_selection_dependency');module.__file__=path;exec(compile(blob,path,'exec'),module.__dict__);return module

def descriptors(preparation):
    require(preparation['schema']=='CASH_TOPUP_NEIGHBOR_PREPARATION_V1','Preparation schema');integer(preparation['scenario_count'],40);require(len(preparation['rows'])==40,'All40 cases')
    integer(preparation['task_evaluation_count'],0);require(preparation['declared_local_neighborhood_complete'] is True,'Complete unevaluated prepared domain')
    out=[];globalpos=0;seen=set()
    for i,row in enumerate(preparation['rows']):
        require(row['scenario_id'] not in seen,'Unique original cases');seen.add(row['scenario_id']);start=0
        require(Path(row['contract_reference']['path'])==PREP/f'scenario-{i:02d}'/'contract.json','Fixed original contract')
        for j,s in enumerate(row['shards']):
            integer(s['start'],start);require(1<=integer(s['stop'])-start<=1000,'Original complete shard range');require(Path(s['path'])==PREP/f'scenario-{i:02d}'/f'tasks-{j:05d}.jsonl','Original task file')
            n=s['stop']-start;out.append(dict(scenario_index=i,shard_index=j,global_shard_index=len(out),global_task_start=globalpos,global_task_stop=globalpos+n,shard=s,contract_reference=row['contract_reference']));globalpos+=n;start=s['stop']
        integer(row['statistics']['new_candidate_count'],start)
    require(len(out)==324 and globalpos==301657,'Full324/301657');return out

def validate_common(d,r,selector):
    p=d['preparation'];queue=descriptors(p);a=d['full_audit']
    selector.audit_gate(dict(reference=r['full_audit'],document=a))
    require(a['reader_sha256']==r['full_audit_reader']['sha256'] and a['source_hashes'].get(r['full_audit_reader']['path'])==r['full_audit_reader']['sha256'],'Combined audit code source')
    require(len(a['logical_shard_reports'])==324,'All original logical shards')
    for i,report in enumerate(a['logical_shard_reports']):
        require(Path(report['path'])==Path(r['full_audit']['path']).parent/f'shard-{i:05d}.json','Fixed combined logical report location')
    for k in FLAGS:
        if k in a:require(a[k] is False,'Full audit no upgraded authority')
    pp=d['preparation_publication'];pa=d['preparation_audit'];require(pp['schema']=='CASH_TOPUP_NEIGHBOR_PREPARATION_PUBLICATION_V1' and pp['status']=='PUBLISHED_UNEVALUATED_CANDIDATES_ONLY','Preparation published')
    require(pa['schema']=='CASH_TOPUP_NEIGHBOR_PREPARATION_INDEPENDENT_READBACK_V1' and pa['status']=='PASS','Preparation audit')
    for v in (pp,pa):exact(v['preparation_reference'],r['preparation'],'Preparation link')
    exact(pa['publication_reference'],r['preparation_publication'],'Preparation receipt audit');exact(pp['source_hashes'],p['source_hashes'],'Original preparation sources')
    for role,key,schema,status in [('previous','result_reference','OLD_HOLDING_TOPUP_PUBLICATION_V1','PUBLISHED_CONDITIONAL_TOPUPS_ONLY'),('paired','account_reference','OLD_HOLDING_TOPUP_PAIRED_ACCOUNT_PUBLICATION_V1','PUBLISHED_CONDITIONAL_PRICE_ONLY_PAIRED_PATHS')]:
        pub=d[role+'_publication'];require(pub['schema']==schema and pub['status']==status,'Saved parent receipt');exact(pub[key],r[role],'Parent reference')
        for flag in ('point_in_time_verified','promotion_allowed','orders_executed'):require(pub[flag] is False,'Parent limitations')
    require(r['previous']['sha256'] in d['previous_review'] and 'PASS' in d['previous_review'],'Saved old review reference')
    first=d['first_audit'];require(first['schema']=='CASH_TOPUP_SINGLE_EVALUATION_INDEPENDENT_READBACK_V1' and first['status']=='PASS' and first['task_id']==FIRST_ID,'Original external audit')
    for key in ('started','raw','postcheck'):exact(first[key+'_reference'],r['first_'+key],'First evidence link')
    return queue

def record_locator(jref,entry):
    return dict(source_reference=jref,byte_start=entry['byte_start'],byte_stop=entry['byte_stop'],record_sha256=entry['record_sha256'],sequence=entry['sequence'],stage=entry['stage'],task_id=entry['task_id'],json_pointer_within_selected_record='/payload')

class Journal:
    def __init__(self,stream,reference,completion,context,task_ids):
        self.stream=stream;self.reference=reference;self.completion=completion;self.context=context;self.ids=task_ids;self.index=0;self.offset=0;self.previous='0'*64;self.hash=hashlib.sha256()
    def take(self,position,stage):
        line=self.stream.readline(16*1024**2+1);require(line.endswith(b'\n') and len(line)<=16*1024**2,'Bounded complete record')
        row=loads(line);require(set(row)=={'schema','sequence','previous_record_sha256','context_sha256','task_id','task_position','stage','payload','record_sha256'},'Exact journal fields')
        require(row['schema']=='CASH_NEIGHBOR_JOURNAL_RECORD_V1' and row['context_sha256']==self.context and row['previous_record_sha256']==self.previous,'Record chain context');integer(row['sequence'],self.index);integer(row['task_position'],position)
        require(row['task_id']==self.ids[position] and row['stage']==stage,'Original task/stage');require(digest({k:v for k,v in row.items() if k!='record_sha256'})==row['record_sha256'] and enc(row)+b'\n'==line,'Canonical journal hash')
        entry=dict(sequence=self.index,byte_start=self.offset,byte_stop=self.offset+len(line),record_sha256=row['record_sha256'],task_id=row['task_id'],stage=row['stage'])
        exact(entry,self.completion['record_index'][self.index],'Original complete byte index');self.hash.update(line);self.offset+=len(line);self.index+=1;self.previous=row['record_sha256']
        return row['payload'],record_locator(self.reference,entry)
    def finish(self):
        require(self.stream.read(1)==b'','No extra journal records');integer(self.completion['record_count'],self.index);require(len(self.completion['record_index'])==self.index and self.completion['terminal_record_sha256']==self.previous,'Complete record partition');exact(self.hash.hexdigest(),self.reference['sha256'],'Whole journal SHA')

def pointer(r,p):return dict(r,json_pointer=p)
def audited(r,a):
    validref(r);require(a['source_hashes'].get(r['path'])==r['sha256'],'Reference not in sealed full audit closure')
def tasks_with_locators(blob,tr):
    rows=[];offset=0
    for line in blob.splitlines(keepends=True):
        require(line.endswith(b'\n'),'Complete task line');t=loads(line);require(enc(t)+b'\n'==line,'Canonical task bytes')
        rows.append((t,dict(source_reference=tr,byte_start=offset,byte_stop=offset+len(line),sha256=sha(line),jsonl_line_index=len(rows))))
        offset+=len(line)
    require(rows,'Nonempty task shard');return rows

def saved_journal(reference,sources,streamed):
    """One original journal, original canonical records; no synthesized stages."""
    size=Path(reference['path']).stat().st_size
    require(size<=128*1024**2,'Bounded single saved journal')
    class Memory(ctypes.Structure):
        _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong)]+[(k,ctypes.c_ulonglong)for k in ('total','available','page_total','page_available','virtual_total','virtual_available','extended')]
    memory=Memory();memory.length=ctypes.sizeof(memory)
    require(os.name=='nt'and ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory))and memory.available>=2*1024**3+32*size,'Measured single-journal memory reserve before reading')
    merge(sources,reference);rows=[];offset=0;previous='0'*64;whole=hashlib.sha256()
    with Path(reference['path']).open('rb') as stream:
        for sequence,line in enumerate(stream):
            require(line.endswith(b'\n') and len(line)<=16*1024**2,'Complete bounded saved journal record')
            row=loads(line);recovery=row['schema']=='CASH_NEIGHBOR_RECOVERY_RECORD_V1'
            require(recovery or row['schema']=='CASH_NEIGHBOR_JOURNAL_RECORD_V1','Known original journal schema')
            integer(row['record_sequence' if recovery else 'sequence'],sequence)
            require(row['previous_record_sha256']==previous and row['record_sha256']==digest({k:v for k,v in row.items()if k!='record_sha256'}) and enc(row)+b'\n'==line,'Original record chain and exact bytes')
            loc=dict(sequence=sequence,byte_start=offset,byte_stop=offset+len(line),record_sha256=row['record_sha256'],task_id=row['task_id'],stage=row['stage'])
            rows.append((row,record_locator(reference,loc)));offset+=len(line);whole.update(line);previous=row['record_sha256']
    exact(whole.hexdigest(),reference['sha256'],'Whole saved journal EOF hash');streamed.add(reference['path']);return rows


def new_records(d,r,queue,prepared,sources,streamed,locator):
    a=d['full_audit']
    for descriptor in queue:
        i=descriptor['global_shard_index'];ar=a['logical_shard_reports'][i]
        report=loads(read(ar,sources));require(report['schema']=='CASH_COMBINED_LOGICAL_SHARD_AUDIT_V1' and report['status']=='PASS','Combined logical report')
        exact(report['descriptor'],descriptor,'Original logical descriptor');integer(report['original_shard_index'],i)
        tr=ref(descriptor['shard']['path'],descriptor['shard']['sha256']);audited(tr,a);tasks=tasks_with_locators(read(tr,sources),tr)
        checked=report['task_results'];integer(report['task_count'],len(tasks));exact([x['task_id']for x in checked],[t['task_id']for t,_ in tasks],'Complete audited original task order')
        evidence=report['evidence'];journals=[];sidecar=None
        if i<279:
            cr=evidence['completion_reference'];audited(cr,a);completion=loads(read(cr,sources));exact(completion['descriptor'],descriptor,'Original complete descriptor')
            sr=evidence['started_reference'];audited(sr,a);read(sr,sources)
            journals=[evidence['journal_reference']]
        elif i==279:
            journals=[evidence['original_partial_journal_reference'],evidence['recovery_journal_reference']]
            sc=evidence['sidecar_reference'];audited(sc,a);sidecar=loads(read(sc,sources))
        else:journals=[evidence['recovery_journal_reference']]
        if i>=279:
            cr=evidence['recovery_completion_reference'];audited(cr,a);completion=loads(read(cr,sources));sr=completion['started_reference'];audited(sr,a);read(sr,sources)
        records_by_task={}
        for jr in journals:
            audited(jr,a)
            for row,loc in saved_journal(jr,sources,streamed):records_by_task.setdefault(row['task_id'],[]).append((row,loc,jr))
        require(set(records_by_task)=={t['task_id']for t,_ in tasks},'All and only logical shard journal tasks')
        for pos,((task,tl),check)in enumerate(zip(tasks,checked)):
            tid=task['task_id'];group=records_by_task[tid];locator.clear();locator.update(task_id=tid,task=tl)
            if tid==FIRST_ID:
                require(i==0 and pos==0 and len(group)==1 and group[0][0]['stage']=='EXTERNAL_REFERENCE','Only original first external')
                expected={k:r[k]for k in ('first_started','first_raw','first_postcheck','first_audit')};exact(group[0][0]['payload'],expected,'Original external evidence')
                raw=d['first_raw'];post=d['first_postcheck'];rawref=r['first_raw'];postref=r['first_postcheck'];locator.update(external_reference_record=group[0][1],external_evidence=expected)
            else:
                missing=i==279 and pos==162
                exact([x[0]['stage']for x in group],['TASK_STARTED','RAW_RETURNED']+([]if missing else['POSTCHECK']),'Original real stage sequence')
                begin,bl,jr=group[0];returned,rl,_=group[1];raw=returned['payload'];rawref=jr
                exact(begin['task_id'],tid,'Started task identity');integer(begin.get('original_shard_task_position',begin.get('task_position')),pos)
                if missing:
                    exact(sidecar['task_id'],tid,'Sidecar task');exact(sidecar['raw_record_reference'],{k:rl[k]for k in ('sequence','byte_start','byte_stop','record_sha256','task_id','stage')},'Sidecar exact original RAW')
                    post=sidecar['independent_postcheck'];postref=evidence['sidecar_reference'];locator.update(sidecar_reference=postref,sidecar_json_pointer='/independent_postcheck')
                else:post=group[2][0]['payload'];postref=group[2][2];locator['postcheck_record']=group[2][1]
                locator.update(started_record=bl,raw_record=rl,journal_schema=begin['schema'])
                exact(post['outcome'],check['outcome'],'Audited outcome');exact(post['original_target_stock_weight_l1'],check['original_target_stock_weight_l1'],'Audited score')
            record=dict(task=task,references=dict(task=tr,raw=rawref,postcheck=postref),shard_audit=dict(reference=ar,document=report),audit_task_index=pos,raw=raw,postcheck=post)
            if tid==FIRST_ID:record['single_audit']=dict(reference=r['first_audit'],document=d['first_audit'])
            yield record


def old_path(previous,paired,index,refs):
    exact(paired['scenario_id'],previous['scenario_id'],'Paired scenario');exact(paired['input_row'],previous['input_row'],'Paired original input');exact(paired['input_reference'],previous['input_reference'],'Paired original input pointer')
    exact(paired['topup_context'],{k:v for k,v in previous.items() if k not in ('evaluation','closure_records','feasible_scores')},'Complete original context')
    exact(paired['topup_context_reference'],pointer(refs['previous'],f'/rows/{index}'),'Paired context source')
    j=previous['selected_candidate_index']
    require(type(j) is int and j>=0,'Saved actual paired selected index')
    plan=previous['evaluation']['branches'][0]['evaluated_plans'][j];exact(paired['selected_plan'],plan,'Original selected plan intact')
    exact(paired['selected_plan_reference'],pointer(refs['previous'],f'/rows/{index}/evaluation/branches/0/evaluated_plans/{j}'),'Original plan pointer')
    require('candidate' in paired['paths'],'Saved candidate path exists')
    return dict(reference=pointer(refs['paired'],f'/rows/{index}/paths/candidate'),scenario_id=previous['scenario_id'],selected_candidate_index=j,buy_shares=deepcopy(plan['buy_shares']))

def streamed_parent_summary(summary,role,r,d):
    require(summary['complete_document_consumed'] is True,'EOF required');integer(summary['row_count'],40);exact(summary['sha256'],r[role]['sha256'],'Complete old source SHA')
    m=summary['metadata'];require(m['schema']==('OLD_HOLDING_TOPUP_CONDITIONAL_RESEARCH_V1' if role=='previous' else 'OLD_HOLDING_TOPUP_PAIRED_PRICE_ONLY_ACCOUNT_V1'),'Complete old source schema')
    exact(m['source_hashes'],d[role+'_publication']['source_hashes'],'Complete old source publication closure')
    for k in ('point_in_time_verified','promotion_allowed','orders_executed'):require(m[k] is False,'Original source limitations')
    if role=='paired':integer(m['scenario_count'],40);integer(m['new_account_path_count'],80)
    return summary

def prepare():
    refs={k:ref(p,h) for k,(p,h) in BOUND.items()}
    # Every future anchor is required before any file is opened.
    for x in refs.values():validref(x)
    sources={str(SOURCE):LOADED};d={};modules={}
    for k,r in refs.items():
        if k in ('previous','paired'):continue
        b=read(r,sources)
        if k in ('selector','json_stream'):modules[k]=private_module(b,r['path'])
        elif k in ('original_policy','full_audit_reader'):pass
        elif k=='previous_review':d[k]=b.decode('utf-8')
        else:d[k]=loads(b)
    require(modules['selector'].PARENT_POLICY_SOURCE_SHA256==refs['original_policy']['sha256'],'Frozen parent policy')
    queue=validate_common(d,refs,modules['selector']);guard(sources)
    return d,refs,queue,sources,modules

def verify_case_outputs(case_refs):
    for entry in case_refs:
        sr=entry['selection_reference'];pr=entry['publication_reference'];lr=entry['ledger_reference'];folder=Path(sr['path']).parent
        require({x.name for x in folder.iterdir()}=={'started.json','ledger.jsonl','selection.json','publication.json'},'Exact case at final closure')
        selected=loads(read(sr,{}));receipt=loads(read(pr,{}))
        exact(receipt['selection_reference'],sr,'Pending case selection');exact(receipt['ledger_reference'],lr,'Pending case ledger');exact(selected['ledger_reference'],lr,'Selected ledger')
        require(receipt['status']==selected['consumption_status']=='PENDING_FINAL_SOURCE_CLOSURE' and receipt['requires_final_publication'] is True and selected['requires_final_publication'] is True,'Case cannot authorize itself')
        exact(receipt['started_reference'],selected['started_reference'],'Case start linkage');read(selected['started_reference'],{})
        h=hashlib.sha256();size=0
        with Path(lr['path']).open('rb') as stream:
            while True:
                b=stream.read(1024*1024)
                if not b:break
                h.update(b);size+=len(b)
        exact(h.hexdigest(),lr['sha256'],'Durable output ledger bytes');integer(selected['ledger_bytes'],size);integer(selected['ledger_row_count'],entry['ledger_row_count'])


def run(*,execute=False):
    require(execute is True,'Explicit preparation-only selection execution');require(not OUTPUT.exists(),'Unique namespace: no retry')
    d,r,queue,sources,modules=prepare();OUTPUT.mkdir(parents=True,exist_ok=False);case=None
    save(OUTPUT/'started.json',dict(schema='CASH_NEIGHBOR_STREAM_SELECTION_STARTED_V1',input_references=r,source_hashes=dict(sources),required_old_candidate_count=2648,required_new_candidate_count=301657,retry_allowed=False,**FLAGS))
    streamed=set();case_refs=[];oldcount=newcount=0;statuses={};locator={}
    try:
        with Path(r['previous']['path']).open('rb') as oldfile,Path(r['paired']['path']).open('rb') as pairfile:
            olds=modules['json_stream'].JsonRowsStream(oldfile);pairs=modules['json_stream'].JsonRowsStream(pairfile)
            for i,oldtoken in enumerate(olds):
                require(i<40,'No extra old scenario');pairtoken=next(pairs,None);require(pairtoken is not None,'Missing paired scenario');integer(pairtoken['row_index'],i)
                previous=oldtoken['value'];paired=pairtoken['value'];row=d['preparation']['rows'][i];exact(previous['scenario_id'],row['scenario_id'],'Original40 order')
                path=old_path(previous,paired,i,r);cr=row['contract_reference'];audited(cr,d['preparation_audit'])
                prepared=loads(read(cr,sources));exact(prepared['contract_sha256'],row['contract_sha256'],'Original scenario contract')
                case=OUTPUT/f'scenario-{i:02d}';case.mkdir(exist_ok=False)
                case_start=save(case/'started.json',dict(schema='CASH_NEIGHBOR_SELECTION_CASE_STARTED_V1',scenario_index=i,scenario_id=row['scenario_id'],contract_reference=cr,contract_sha256=row['contract_sha256'],previous_row_reference=pointer(r['previous'],f'/rows/{i}'),paired_row_reference=pointer(r['paired'],f'/rows/{i}'),requires_final_publication=True,**FLAGS))
                ledgerhash=hashlib.sha256();ledgerbytes=ledgerrows=0
                with (case/'ledger.jsonl').open('xb') as output:
                    def emit(value):
                        nonlocal ledgerbytes,ledgerrows
                        if value['origin']=='OLD':
                            loc=dict(source_reference=r['previous'],byte_start=oldtoken['byte_start'],byte_stop=oldtoken['byte_stop'],row_sha256=oldtoken['sha256'],row_index=i,json_pointer_within_selected_row=f'/evaluation/branches/0/evaluated_plans/{value["identity"]["old_candidate_index"]}')
                        else:
                            require(locator['task_id']==value['identity']['task_id'],'Current task locator');loc=deepcopy(locator)
                        line=enc(dict(selection_ledger_row=value,source_locator=loc))+b'\n';output.write(line);ledgerhash.update(line);ledgerbytes+=len(line);ledgerrows+=1
                    selected=modules['selector'].select_scenario_stream(prepared=prepared,previous_row=previous,new_records=new_records(d,r,[x for x in queue if x['scenario_index']==i],prepared,sources,streamed,locator),expected_new_count=row['statistics']['new_candidate_count'],old_selected_path=path,full_audit=dict(reference=r['full_audit'],document=d['full_audit']),tie_policy=modules['selector'].POLICY,emit_ledger_row=emit)
                    output.flush();os.fsync(output.fileno())
                integer(selected['ledger_emitted_row_count'],ledgerrows);oldcount+=selected['old_candidate_count'];newcount+=selected['new_candidate_count'];statuses[selected['status']]=statuses.get(selected['status'],0)+1
                lr=ref(case/'ledger.jsonl',ledgerhash.hexdigest())
                sr=save(case/'selection.json',dict(schema='CASH_NEIGHBOR_SOURCE_BOUND_CASE_SELECTION_V1',scenario_index=i,selection=selected,ledger_reference=lr,ledger_bytes=ledgerbytes,ledger_row_count=ledgerrows,started_reference=case_start,full_audit_reference=r['full_audit'],consumption_status='PENDING_FINAL_SOURCE_CLOSURE',requires_final_publication=True,source_number_semantics='JSON_NATIVE_VALUES_PRESERVED_ORIGINAL_BYTE_SPANS_AND_HASHES_ARE_EXACT',**FLAGS))
                pr=save(case/'publication.json',dict(schema='CASH_NEIGHBOR_SELECTION_CASE_RECEIPT_V1',status='PENDING_FINAL_SOURCE_CLOSURE',selection_reference=sr,ledger_reference=lr,started_reference=case_start,requires_final_publication=True,**FLAGS))
                require({x.name for x in case.iterdir()}=={'started.json','ledger.jsonl','selection.json','publication.json'},'Exact pending case files')
                case_refs.append(dict(scenario_index=i,scenario_id=row['scenario_id'],selection_reference=sr,publication_reference=pr,ledger_reference=lr,ledger_row_count=ledgerrows,status=selected['status']))
                del previous,paired,oldtoken,pairtoken,prepared,selected;case=None
            require(next(pairs,None) is None,'No extra paired scenario')
            summaries={role:streamed_parent_summary(iterator.summary,role,r,d) for role,iterator in [('previous',olds),('paired',pairs)]}
        for role in ('previous','paired'):merge(sources,r[role]);streamed.add(r[role]['path'])
        require(len(case_refs)==40 and oldcount==2648 and newcount==301657,'Complete304305 declared union')
        verify_case_outputs(case_refs)
        guard({p:h for p,h in sources.items() if p not in streamed})
        result=dict(schema='CASH_NEIGHBOR_COMBINED_STREAM_SELECTION_INDEX_V1',status='COMPLETE_DECLARED_UNION_SELECTION',cases=case_refs,scenario_count=40,old_candidate_count=oldcount,new_candidate_count=newcount,total_candidate_count=oldcount+newcount,status_counts=statuses,input_references=r,source_hashes=sources,streamed_source_paths=sorted(streamed),source_authentication_scope='EXACT_CONSUMED_BYTES_ONCE_AT_EOF_NOT_CONTINUOUS_MONITORING_OR_TRANSITIVE_REAUDIT',old_stream_summaries=summaries,case_receipts_authorized_only_by_this_final_publication=True,full_audit_source_hashes_preserved_not_reaudited=d['full_audit']['source_hashes'],selection_policy=modules['selector'].POLICY,**FLAGS)
        ir=save(OUTPUT/'index.json',result);pr=save(OUTPUT/'publication.json',dict(schema='CASH_NEIGHBOR_COMBINED_STREAM_SELECTION_PUBLICATION_V1',status='PUBLISHED_COMPLETE_DECLARED_UNION_SELECTION',index_reference=ir,source_hashes=sources,case_count=40,**FLAGS))
        guard({p:h for p,h in sources.items() if p not in streamed})
        require(sha(Path(ir['path']).read_bytes())==ir['sha256'] and sha(Path(pr['path']).read_bytes())==pr['sha256'],'Final index and receipt bytes')
        require({x.name for x in OUTPUT.iterdir()}=={'started.json','index.json','publication.json'}|{f'scenario-{i:02d}' for i in range(40)},'Exact complete output namespace')
        return dict(ir,publication_reference=pr)
    except BaseException as e:
        failure=dict(schema='CASH_NEIGHBOR_STREAM_SELECTION_FAILURE_V1',error_type=type(e).__name__,error=str(e),all_case_prefixes_unconsumable=True,retry_allowed=False,**FLAGS)
        if case is not None and case.exists() and not (case/'failure.json').exists():save(case/'failure.json',failure)
        if not (OUTPUT/'failure.json').exists():save(OUTPUT/'failure.json',failure)
        raise

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');args=parser.parse_args();print(json.dumps(run(execute=args.execute)))
