"""Independent saved-ledger selection verification. No selector/evaluator imports.

Only saved scores are ordered. Source spans are read as evidence; no arithmetic
risk, fee, L1, account or return evaluation is performed. Future anchors fail shut.
"""
import argparse
import hashlib
import json
import os
import re
from collections import OrderedDict
from fractions import Fraction
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SOURCE=Path(__file__).resolve()
LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
PARENT=ROOT/'data/cache/research/cash_neighbor_selection_20261003_v1'
OUTPUT=ROOT/'data/cache/research/cash_neighbor_selection_independent_readback_20261003_v1'
BOUND={'index':(str(PARENT/'index.json'),None),'publication':(str(PARENT/'publication.json'),None),'producer':(str(ROOT/'scripts/ndx_cash_neighbor_selection_20261003.py'),None)}
PREP=ROOT/'data/cache/research/cash_topup_neighbor_preparation_20261003_v1'
FIRST_ID='8b5320eb5ac613ddf6a69478f7e2360811688d1951b38c9e1d7b4ff34678febd'
FIRST_ROOT=ROOT/'data/cache/research/cash_topup_neighbor_evaluation_20261003_v1'/FIRST_ID
INPUT_BOUND={
 'preparation':(str(PREP/'preparation.json'),'04cf54101f56303cc656e60079f1434661845da6e13c6c7d23305f3e9f1dde2b'),
 'preparation_publication':(str(PREP/'publication.json'),'dbe1e731c02293dab4a5cca4f0fa7fbf84367cd201dbf90b9e703cab1fd86b53'),
 'preparation_audit':(str(ROOT/'data/cache/research/cash_topup_neighbor_preparation_independent_readback_20261003_v1/independent_readback.json'),'c29c98c5c48d61e2533c7a587291932eda3b5776d81a9d0288a75a6b7d891ce8'),
 'previous':(str(ROOT/'data/cache/research/old_holding_topup_research_20261002_v1/results.json'),'1192aa5876b8ea9e36c84ad33d88f5504df849e8612312f1886fad6b579351fb'),
 'previous_publication':(str(ROOT/'data/cache/research/old_holding_topup_research_20261002_v1/publication.json'),'ed4f230d5e74ac0fb2000149caab80825e48d36cf3d7cd98a5f0858abc0fbc16'),
 'previous_review':(str(ROOT/'DYNAMIC_OLD_HOLDING_TOPUP_INDEPENDENT_READBACK_20261002.md'),'40f02f234a2661b0c3e0bb0ed2e7456a038d664c2e0e631561826f7b1e57f9ec'),
 'paired':(str(ROOT/'data/cache/research/old_holding_topup_paired_account_20261002_v1/accounts.json'),'7d5df8f295657497f3919aa3458dff31f0c175a40f391eb6b37ac9e5b7512d6f'),
 'paired_publication':(str(ROOT/'data/cache/research/old_holding_topup_paired_account_20261002_v1/publication.json'),'fb9db1ac77fffec7ec90141a7b431b3f34fb4bac0329deb07245c85b22325e7e'),
 'full_result':(None,None),'full_audit':(None,None),'full_audit_reader':(str(ROOT/'scripts/ndx_cash_topup_neighbor_full_independent_readback_20261003.py'),None),
 'first_started':(str(FIRST_ROOT/'started.json'),'b2d44ac6acff14561f325fa1b3fa859895e253475bd924c764a7eeba6766ff3a'),
 'first_raw':(str(FIRST_ROOT/'raw.json'),'9dd01e5f9fc167f462c00c7858b89de51d540b810c0a2b5a3d0b18fc5d04719c'),
 'first_postcheck':(str(FIRST_ROOT/'postcheck.json'),'7df4aa5f7285af105bcca01cafa2e132c0c0a3b15eca8bc0d7ae9b78615a0a57'),
 'first_audit':(str(ROOT/'data/cache/research/cash_topup_neighbor_single_evaluation_independent_readback_20261003_v1'/FIRST_ID/'independent_readback.json'),'942edc8840a4ff81b273988663b8e3318e12453076ba4034ad1a26412368b411'),
 'selector':(str(ROOT/'backtest/ndx_cash_neighbor_stream_selection_research.py'),'ec448eae9f93e33751640ac3f17fadad5cb19764aa8c6bfd94154a510ccb37b5'),
 'original_policy':(str(ROOT/'backtest/ndx_cash_neighbor_selection_research.py'),'7c44c7fcedd298bb75eed2e9e94cd5587bff31cb0771947a7b540683e21a3879'),
 'json_stream':(str(ROOT/'backtest/ndx_research_json_rows_stream.py'),'b1a2ae63c68476dc952abf53bdd081e7f08cab3052ddc6fca5b61bd32091b86c')}
POLICY='OLD_ORIGINAL_INDEX_THEN_NEW_FROZEN_SCENARIO_ORDINAL_V1'
FIRST='8b5320eb5ac613ddf6a69478f7e2360811688d1951b38c9e1d7b4ff34678febd'
FLAGS={k:False for k in ('risk_recomputed','fees_recomputed','l1_recomputed','fit_performed','account_executed','orders_executed','point_in_time_verified','promotion_allowed','global_optimality_claimed','fresh_oos_claimed','old_audits_reexecuted','full_transitive_source_closure_reverified')}
PURE_FALSE=('source_bytes_authenticated','point_in_time_verified','promotion_allowed','orders_executed','account_executed','risk_recomputed','fees_recomputed','l1_recomputed','time_series_return_evaluated','global_optimality_claimed','fresh_oos_claimed')

def require(ok,msg):
    if not ok:raise ValueError(msg)
def enc(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(b):return hashlib.sha256(b).hexdigest()
def exact(a,b,msg='Exact saved evidence'):require(enc(a)==enc(b),msg)
def integer(x,n=None):require(type(x) is int and x>=0 and (n is None or x==n),'Exact nonnegative count');return x
def pairs(xs):
    d={}
    for k,v in xs:require(k not in d,'Duplicate JSON key');d[k]=v
    return d
def loads(b):return json.loads(b,object_pairs_hook=pairs,parse_constant=lambda v:(_ for _ in ()).throw(ValueError(v)))
def ref(p,h):return dict(path=str(p),sha256=h)
def valid(r):
    require(type(r) is dict and set(r) in ({'path','sha256'},{'path','sha256','json_pointer'}),'Reference shape')
    require(type(r['path']) is str and bool(r['path']) and r['path']==r['path'].strip(),'Reference path')
    require(type(r['sha256']) is str and re.fullmatch('[0-9a-f]{64}',r['sha256']),'Pending or invalid SHA')
    if 'json_pointer' in r:require(type(r['json_pointer']) is str and r['json_pointer'].startswith('/'),'Explicit JSON pointer')
    return r
def flags(v):
    for k in FLAGS:require(v[k] is False,'Authority '+k)
def hash_file(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
def read(r):valid(r);b=Path(r['path']).read_bytes();require(sha(b)==r['sha256'],'Source bytes');return loads(b)
def merge(d,r):
    valid(r);require(r['path'] not in d or d[r['path']]==r['sha256'],'Source conflict');d[r['path']]=r['sha256']
def ratio(v):
    require(type(v) is dict and set(v)=={'numerator','denominator'},'Saved score pair')
    a=integer(v['numerator']);b=integer(v['denominator']);require(b>0,'Positive denominator');return Fraction(a,b)
def pointer(v,p):
    for t in p.lstrip('/').split('/'):
        t=t.replace('~1','/').replace('~0','~');v=v[int(t)] if isinstance(v,list) else v[t]
    return v

class Evidence:
    """At most three open source handles; authenticate full hashes separately once."""
    def __init__(self,sources):self.sources=sources;self.handles=OrderedDict()
    def span(self,loc,record=False):
        r=valid(loc['source_reference']);require(self.sources.get(r['path'])==r['sha256'],'Locator source closure')
        start=integer(loc['byte_start']);stop=integer(loc['byte_stop']);require(0<stop-start<=32*1024**2,'Bounded source span')
        if r['path'] not in self.handles:
            if len(self.handles)==3:self.handles.popitem(last=False)[1].close()
            self.handles[r['path']]=Path(r['path']).open('rb')
        f=self.handles[r['path']];f.seek(start);b=f.read(stop-start);require(len(b)==stop-start,'Complete source span');v=loads(b)
        if record:
            exact(loc['json_pointer_within_selected_record'],'/payload')
            exact(sha(enc({k:x for k,x in v.items() if k!='record_sha256'})),v['record_sha256'])
            exact(v['record_sha256'],loc['record_sha256']);exact(v['sequence'],loc['sequence']);exact(v['stage'],loc['stage']);exact(v['task_id'],loc['task_id'])
            require(enc(v)+b'\n'==b,'Canonical journal span');return v['payload']
        exact(sha(b),loc.get('row_sha256',loc.get('sha256')));return v
    def close(self):
        for f in self.handles.values():f.close()


def inspect_case(stream,selection,entry,contract,check_evidence=None):
    """One ledger pass, independent lexicographic saved-score minimum, bounded sets."""
    require(selection['schema']=='CASH_NEIGHBOR_SOURCE_BOUND_CASE_SELECTION_V1','Case schema');flags(selection)
    require(selection['consumption_status']=='PENDING_FINAL_SOURCE_CLOSURE' and selection['requires_final_publication'] is True,'Case not self-authorizing')
    integer(selection['scenario_index'],entry['scenario_index']);s=selection['selection'];exact(s['parent_policy_source_sha256'],'7c44c7fcedd298bb75eed2e9e94cd5587bff31cb0771947a7b540683e21a3879');require(s['schema']=='CASH_NEIGHBOR_STREAM_SCENARIO_SELECTION_V1' and s['tie_policy']==POLICY,'Frozen rule')
    for k in PURE_FALSE:require(s[k] is False,'Pure scope')
    require(s['selection_performed'] is True and s['ledger_storage_external'] is True and s['ledger_emitter_source_authenticated'] is False and s['emitted_prefix_valid_only_after_successful_return'] is True,'Stream contract')
    require(s['scope']=='BEST_IN_COMPLETE_DECLARED_UNION_NOT_GLOBAL_OPTIMUM','Bounded scope')
    old=integer(s['old_candidate_count']);new=integer(s['new_candidate_count']);total=old+new
    for k in ('total_candidate_count','ledger_emitted_row_count'):integer(s[k],total)
    integer(selection['ledger_row_count'],total);integer(entry['ledger_row_count'],total)
    exact(s['scenario_id'],entry['scenario_id']);exact(s['contract_sha256'],sha(enc(contract)))
    ids=contract['conditional_research_buy_ids'];require(ids==sorted(set(ids)) and ids,'Complete canonical buy domain')
    require(set(contract['saved_buy_limits'])==set(ids),'Full cap domain')
    exact(len(contract['old_evaluated_points']),old)
    seen=set();tids=set();best=None;oldbest=None;winner=None;feasible=0;n=0;size=0;h=hashlib.sha256()
    for b in stream:
        require(b.endswith(b'\n') and len(b)<=32*1024**2,'Bounded complete ledger row')
        envelope=loads(b);require(set(envelope)=={'selection_ledger_row','source_locator'} and enc(envelope)+b'\n'==b,'Canonical ledger envelope')
        row=envelope['selection_ledger_row'];loc=envelope['source_locator'];require(n<total,'Extra candidate')
        integer(row['merged_candidate_index'],n);origin='OLD' if n<old else 'NEW';exact(row['origin'],origin)
        plan=row['saved_plan'];exact(plan['buy_shares'],row['buy_shares']);exact(plan['feasible'],row['feasible']);require(type(row['feasible']) is bool,'Exact feasible boolean')
        require(set(row['buy_shares'])==set(ids),'Full vector');vector=tuple(integer(row['buy_shares'][x]) for x in ids)
        require(all(q<=integer(contract['saved_buy_limits'][x]) for x,q in zip(ids,vector)),'Original caps');require(vector not in seen,'No duplicate union point');seen.add(vector)
        if origin=='OLD':
            exact(row['identity'],{'old_candidate_index':n});integer(plan['supplied_plan_index'],n)
            point=contract['old_evaluated_points'][n];integer(point['candidate_index'],n);exact(point['buy_shares'],row['buy_shares']);exact(point['saved_feasible'],row['feasible']);exact(row['references'],{'plan':point['reference']})
            integer(loc['row_index'],entry['scenario_index']);exact(loc['json_pointer_within_selected_row'],f'/evaluation/branches/0/evaluated_plans/{n}')
        else:
            task=row['identity'];integer(task['scenario_candidate_ordinal'],n-old);exact(task['scenario_id'],entry['scenario_id'])
            identity=dict(schema='CONDITIONAL_TOPUP_NEIGHBOR_TASK_IDENTITY_V1',rule=contract['rule'],scenario_contract_sha256=s['contract_sha256'],buy_shares=row['buy_shares'])
            exact(task['identity'],identity);exact(task['task_id'],sha(enc(identity)));require(task['task_id'] not in tids,'Unique task');tids.add(task['task_id']);integer(plan['supplied_plan_index'],0);exact(loc['task_id'],task['task_id'])
        key=None
        if row['feasible']:
            score=row['saved_score'];require(type(score) is dict and set(score)=={'distance','fees_usd'},'Saved score fields')
            require(type(plan['fees_usd']) is str,'Literal saved fee');key=(ratio(score['distance']),ratio(score['fees_usd']),n)
            exact(Fraction(plan['fees_usd'])==key[1],True);feasible+=1
            if best is None or key<best:best=key;winner=loads(enc(row))
            if origin=='OLD' and (oldbest is None or key<oldbest):oldbest=key
        else:require(row['saved_score'] is None,'Infeasible score absent')
        if check_evidence is not None:check_evidence(row,loc)
        n+=1;size+=len(b);h.update(b)
    integer(n,total);integer(size,selection['ledger_bytes']);exact(h.hexdigest(),selection['ledger_reference']['sha256']);exact(selection['ledger_reference'],entry['ledger_reference'])
    integer(s['feasible_candidate_count'],feasible);exact(s['selected'],winner)
    oldindex=None if oldbest is None else oldbest[2];exact(contract['original_selected_candidate_index'],oldindex)
    path=s['old_selected_path']
    if oldindex is None:require(path is None,'No invented old path')
    else:
        valid(path['reference']);exact(path['scenario_id'],entry['scenario_id']);integer(path['selected_candidate_index'],oldindex);exact(path['buy_shares'],contract['old_evaluated_points'][oldindex]['buy_shares'])
    reuse=winner is not None and path is not None and winner['buy_shares']==path['buy_shares']
    status='NO_FEASIBLE_IN_DECLARED_UNION' if winner is None else ('REUSE_EXISTING_PAIRED_PATH' if reuse else 'NEW_PATH_REQUIRED')
    exact(s['status'],status);exact(entry['status'],status);exact(s['reused_path_reference'],path['reference'] if reuse else None)
    return dict(scenario_index=entry['scenario_index'],scenario_id=entry['scenario_id'],old_candidate_count=old,new_candidate_count=new,total_candidate_count=n,feasible_candidate_count=feasible,status=status,selected_merged_candidate_index=None if best is None else best[2],ledger_sha256=h.hexdigest(),ledger_bytes=size)


def validate_old_path(selection_path,paired_row,previous_row,index,refs):
    integer(index);j=integer(previous_row['selected_candidate_index'])
    expected=dict(refs['paired'],json_pointer=f'/rows/{index}/paths/candidate')
    require(type(selection_path) is dict,'Saved original selected path')
    exact(selection_path['reference'],expected)
    exact(selection_path['scenario_id'],previous_row['scenario_id']);integer(selection_path['selected_candidate_index'],j)
    exact(paired_row['scenario_id'],previous_row['scenario_id'])
    exact(paired_row['input_row'],previous_row['input_row']);exact(paired_row['input_reference'],previous_row['input_reference'])
    exact(paired_row['topup_context'],{k:v for k,v in previous_row.items() if k not in ('evaluation','closure_records','feasible_scores')})
    exact(paired_row['topup_context_reference'],dict(refs['previous'],json_pointer=f'/rows/{index}'))
    plan=previous_row['evaluation']['branches'][0]['evaluated_plans'][j]
    exact(paired_row['selected_plan'],plan);exact(selection_path['buy_shares'],plan['buy_shares'])
    exact(paired_row['selected_plan_reference'],dict(refs['previous'],json_pointer=f'/rows/{index}/evaluation/branches/0/evaluated_plans/{j}'))
    require(type(paired_row['paths']['candidate']) is dict,'Saved actual candidate path')


def iter_json_rows(reference):
    """Independent incremental top-level JSON rows parser; never holds the 40 paths."""
    valid(reference)
    with Path(reference['path']).open('rb') as f:
        import codecs
        utf=codecs.getincrementaldecoder('utf-8')('strict');decoder=json.JSONDecoder(object_pairs_hook=pairs,parse_constant=lambda x:(_ for _ in ()).throw(ValueError(x)))
        buffer='';eof=False;h=hashlib.sha256()
        def more():
            nonlocal buffer,eof
            raw=f.read(65536);h.update(raw)
            eof=not raw;buffer+=utf.decode(raw,final=eof)
        def trim():
            nonlocal buffer
            buffer=buffer.lstrip()
            while not buffer and not eof:more();buffer=buffer.lstrip()
        def char(expected):
            nonlocal buffer
            trim();require(buffer.startswith(expected),'JSON structural delimiter');buffer=buffer[len(expected):]
        def value():
            nonlocal buffer
            trim()
            while True:
                try:v,end=decoder.raw_decode(buffer);break
                except json.JSONDecodeError:
                    require(not eof and len(buffer)<64*1024**2,'Complete bounded JSON value');more()
            # Ensure a primitive was not accepted at an artificial chunk boundary.
            while end==len(buffer) and not eof:
                more();v,end=decoder.raw_decode(buffer)
            buffer=buffer[end:];return v
        char('{');keys=set();saw=False
        while True:
            trim()
            if buffer.startswith('}'):char('}');break
            key=value();require(type(key) is str and key not in keys,'Unique object key');keys.add(key);char(':')
            if key=='rows':
                require(not saw,'Single rows array');saw=True;char('[');first=True
                while True:
                    trim()
                    if buffer.startswith(']'):char(']');break
                    if not first:char(',')
                    row=value();require(type(row) is dict,'Object row');yield row;first=False
            else:value()
            trim()
            if buffer.startswith('}'):char('}');break
            char(',');trim();require(not buffer.startswith('}'),'No trailing object comma')
        trim();require(eof and not buffer and saw,'Complete JSON object EOF');exact(h.hexdigest(),reference['sha256'],'Whole paired source hash')


def save(path,v):
    b=enc(v)
    with path.open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
    require(path.read_bytes()==b,'Saved readback bytes');return ref(path,sha(b))


def readback(*,execute=False):
    require(execute is True,'Explicit independent readback');require(not OUTPUT.exists(),'Create only; no retry')
    refs={k:valid(ref(p,h)) for k,(p,h) in BOUND.items()}
    index=read(refs['index']);pub=read(refs['publication']);require(hash_file(refs['producer']['path'])==refs['producer']['sha256'],'Producer source anchor')
    require(index['schema']=='CASH_NEIGHBOR_STREAM_SELECTION_INDEX_V1' and index['status']=='COMPLETE_DECLARED_UNION_SELECTION','Full final index')
    require(pub['schema']=='CASH_NEIGHBOR_STREAM_SELECTION_PUBLICATION_V1' and pub['status']=='PUBLISHED_COMPLETE_DECLARED_UNION_SELECTION','Final publication mandatory')
    exact(pub['index_reference'],refs['index']);exact(pub['source_hashes'],index['source_hashes']);flags(index);flags(pub);integer(pub['case_count'],40)
    require(index['case_receipts_authorized_only_by_this_final_publication'] is True and index['selection_policy']==POLICY,'Final EOF authorization')
    for k,v in dict(scenario_count=40,old_candidate_count=2648,new_candidate_count=301657,total_candidate_count=304305).items():integer(index[k],v)
    require({p.name for p in PARENT.iterdir()}=={'started.json','index.json','publication.json'}|{f'scenario-{i:02d}' for i in range(40)},'Exact successful parent namespace')
    started=loads((PARENT/'started.json').read_bytes());exact(started['input_references'],index['input_references']);flags(started)
    inputs=index['input_references'];exact(inputs,{k:valid(ref(p,h)) for k,(p,h) in INPUT_BOUND.items()},'Fixed eighteen parent roles');base={refs['producer']['path']:refs['producer']['sha256']}
    for r in inputs.values():merge(base,r)
    exact(started['source_hashes'],{k:v for k,v in base.items() if k not in (inputs['previous']['path'],inputs['paired']['path'])})
    expected=dict(base);preparation=read(inputs['preparation']);audit=read(inputs['full_audit']);result=read(inputs['full_result'])
    require(audit['status']=='PASS' and audit['schema']=='CASH_NEIGHBOR_FULL_BATCH_INDEPENDENT_READBACK_V1','Full independent parent audit');exact(audit['result_reference'],inputs['full_result']);exact(audit['reader_sha256'],inputs['full_audit_reader']['sha256']);require(audit['source_hashes'].get(inputs['full_audit_reader']['path'])==inputs['full_audit_reader']['sha256'],'Full audit reader binding')
    exact(index['full_audit_source_hashes_preserved_not_reaudited'],audit['source_hashes'])
    streamed={inputs['previous']['path'],inputs['paired']['path']}
    for row in preparation['rows']:
        merge(expected,row['contract_reference'])
        for r in row['shards']:merge(expected,ref(r['path'],r['sha256']))
    for r in result['completed_shard_references']:
        merge(expected,r);c=read(r)
        for key in ('started_reference','journal_reference'):merge(expected,c[key])
        streamed.add(c['journal_reference']['path'])
    for r in audit['shard_audit_references']:merge(expected,r)
    exact(expected,index['source_hashes']);exact(sorted(streamed),index['streamed_source_paths'])
    for role in ('previous','paired'):
        v=index['old_stream_summaries'][role];require(v['complete_document_consumed'] is True,'Old EOF witness');integer(v['row_count'],40);exact(v['sha256'],inputs[role]['sha256'])
    for p,h in expected.items():
        if p!=inputs['paired']['path']:require(hash_file(p)==h,'Full direct source hash '+p)
    # The paired source is authenticated at the independent streaming parser EOF below.
    evidence=Evidence(expected);OUTPUT.mkdir(parents=True,exist_ok=False)
    save(OUTPUT/'started.json',dict(input_references=refs,reader_sha256=LOADED,**FLAGS))
    reports=[];counts={};oldcache={};paired_rows=iter_json_rows(inputs['paired'])
    try:
        for i,entry in enumerate(index['cases']):
            integer(entry['scenario_index'],i);exact(entry['scenario_id'],preparation['rows'][i]['scenario_id']);require(i<40,'No extra scenario');folder=PARENT/f'scenario-{i:02d}'
            require({p.name for p in folder.iterdir()}=={'started.json','ledger.jsonl','selection.json','publication.json'},'Exact pending case namespace')
            for k,name in (('selection_reference','selection.json'),('publication_reference','publication.json'),('ledger_reference','ledger.jsonl')):exact(entry[k]['path'],str(folder/name))
            selection=read(entry['selection_reference']);integer(selection['selection']['new_candidate_count'],preparation['rows'][i]['statistics']['new_candidate_count']);exact(selection['full_audit_reference'],inputs['full_audit']);exact(selection['selection']['full_audit_reference'],inputs['full_audit']);receipt=read(entry['publication_reference']);flags(receipt)
            require(receipt['schema']=='CASH_NEIGHBOR_SELECTION_CASE_RECEIPT_V1','Case receipt schema');require(receipt['status']=='PENDING_FINAL_SOURCE_CLOSURE' and receipt['requires_final_publication'] is True,'Pending receipt scope');exact(receipt['selection_reference'],entry['selection_reference']);exact(receipt['ledger_reference'],entry['ledger_reference']);exact(receipt['started_reference'],selection['started_reference'])
            cs=read(selection['started_reference']);exact(cs['scenario_id'],entry['scenario_id']);integer(cs['scenario_index'],i);exact(cs['contract_reference'],preparation['rows'][i]['contract_reference']);flags(cs)
            prepared=read(cs['contract_reference']);contract=prepared['contract'];exact(prepared['contract_sha256'],sha(enc(contract)));exact(cs['contract_sha256'],prepared['contract_sha256']);oldpath=selection['selection']['old_selected_path'];
            if oldpath is not None:exact(oldpath['reference'],dict(inputs['paired'],json_pointer=f'/rows/{i}/paths/candidate'))
            oldcache.clear();paired_row=next(paired_rows);exact(paired_row['scenario_id'],entry['scenario_id']);exact(paired_row['selected_plan_reference'],dict(inputs['previous'],json_pointer=f'/rows/{i}/evaluation/branches/0/evaluated_plans/{contract["original_selected_candidate_index"]}'));exact(paired_row['topup_context_reference'],dict(inputs['previous'],json_pointer=f'/rows/{i}'))
            def check(row,loc):
                if row['origin']=='OLD':
                    exact(loc['source_reference'],inputs['previous']);integer(loc['row_index'],i)
                    if not oldcache:
                        original=evidence.span(loc);validate_old_path(oldpath,paired_row,original,i,inputs);oldcache.update(row=original,locator=loc)
                    exact(loc,{**oldcache['locator'],'json_pointer_within_selected_row':loc['json_pointer_within_selected_row']});original=oldcache['row'];exact(original['selected_candidate_index'],contract['original_selected_candidate_index']);j=row['identity']['old_candidate_index'];exact(original['scenario_id'],entry['scenario_id']);exact(pointer(original,loc['json_pointer_within_selected_row']),row['saved_plan'])
                    scores={x['candidate_index']:{k:x[k] for k in ('distance','fees_usd')} for x in original['feasible_scores']};exact(scores.get(j),row['saved_score'])
                else:
                    task=evidence.span(loc['task']);exact(task,row['identity']);r=row['references'];exact(r['task'],loc['task']['source_reference']);require(r['shard_audit'] in audit['shard_audit_references'],'Audited shard reference')
                    if task['task_id']==FIRST:
                        external=evidence.span(loc['external_reference_record'],True);exact(external,loc['external_evidence']);exact(external,{k:inputs[k] for k in ('first_started','first_raw','first_postcheck','first_audit')});exact(r['single_audit'],inputs['first_audit'])
                        raw=read(inputs['first_raw']);post=read(inputs['first_postcheck']);exact(r['raw'],inputs['first_raw']);exact(r['postcheck'],inputs['first_postcheck'])
                    else:
                        require(r['single_audit'] is None,'Only first external audit');begin=evidence.span(loc['started_record'],True);exact(loc['started_record']['stage'],'TASK_STARTED');exact(loc['started_record']['task_id'],task['task_id']);exact(begin['task_reference'],dict(r['task'],jsonl_line_index=loc['task']['jsonl_line_index'],scenario_candidate_ordinal=task['scenario_candidate_ordinal']));raw=evidence.span(loc['raw_record'],True);post=evidence.span(loc['postcheck_record'],True)
                        for k,stage in (('raw_record','RAW_RETURNED'),('postcheck_record','POSTCHECK')):exact(loc[k]['stage'],stage);exact(loc[k]['task_id'],task['task_id'])
                        exact(r['raw'],loc['raw_record']['source_reference']);exact(r['postcheck'],loc['postcheck_record']['source_reference'])
                    integer(raw['explicit_evaluator_call_attempt_count'],1);integer(raw['returned_evaluation_count'],1);require(raw['error'] is None and post['evaluation_error'] is None and post['validation_error'] is None,'Technical failure cannot compete')
                    exact(raw['result']['branches'][0]['evaluated_plans'][0],row['saved_plan']);exact(post['original_target_stock_weight_l1'],row['saved_score']);exact(post['outcome'],'FEASIBLE' if row['feasible'] else 'INFEASIBLE')
            with (folder/'ledger.jsonl').open('rb') as f:report=inspect_case(f,selection,entry,contract,check)
            reports.append(report);counts[report['status']]=counts.get(report['status'],0)+1
        require(next(paired_rows,None) is None,'No extra paired rows');integer(len(reports),40)
        for k,v in dict(old_candidate_count=2648,new_candidate_count=301657,total_candidate_count=304305).items():integer(sum(x[k] for x in reports),v)
        exact(counts,index['status_counts']);require(hash_file(SOURCE)==LOADED,'Reader drift')
        for r in refs.values():require(hash_file(r['path'])==r['sha256'],'Final outer anchor drift')
        report=dict(schema='CASH_NEIGHBOR_SELECTION_INDEPENDENT_READBACK_V1',status='PASS',index_reference=refs['index'],publication_reference=refs['publication'],reader_sha256=LOADED,source_hashes={**expected,**{r['path']:r['sha256'] for r in refs.values()},str(SOURCE):LOADED},scenario_count=40,total_candidate_count=304305,cases=reports,status_counts=counts,complete_saved_score_order_independently_verified=True,original_source_spans_compared_without_evaluation=True,started_has_external_sha_anchor=False,source_scope='DIRECT_BYTES_ONCE_PLUS_REFERENCED_SPANS;NOT_CONTINUOUS_MONITORING_OR_OLD_AUDIT_REEXECUTION',**FLAGS)
        rr=save(OUTPUT/'independent_readback.json',report);require({p.name for p in OUTPUT.iterdir()}=={'started.json','independent_readback.json'},'Exact readback namespace');return rr
    except BaseException as e:
        save(OUTPUT/'failure.json',dict(status='FAILED_DO_NOT_CONSUME',error_type=type(e).__name__,error=str(e),retry_allowed=False,**FLAGS));raise
    finally:evidence.close();paired_rows.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');print(json.dumps(readback(execute=p.parse_args().execute)))
