"""Independent saved local-neighborhood readback; never evaluate financial risk."""
import argparse,hashlib,json,os,re
from copy import deepcopy
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];SOURCE=Path(__file__).resolve();LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
DIRECTORY=ROOT/'data/cache/research/cash_topup_neighbor_preparation_20261003_v1'
OUTPUT=ROOT/'data/cache/research/cash_topup_neighbor_preparation_independent_readback_20261003_v1'
PREPARATION_SHA='04cf54101f56303cc656e60079f1434661845da6e13c6c7d23305f3e9f1dde2b'
PUBLICATION_SHA='dbe1e731c02293dab4a5cca4f0fa7fbf84367cd201dbf90b9e703cab1fd86b53'
PARENTS={
'inputs':('data/cache/research/remaining_standard_cash_inputs_20261002_v1/inputs.json','1143482cc4d610c6bd3976f846730b98ef1f11148e3b1f5eb008135a5faea1e5'),
'inputs_publication':('data/cache/research/remaining_standard_cash_inputs_20261002_v1/publication.json','54d6f6d2771dc4caf85c07b2b8a28e33e1a50a3aace1df99308c012ae1ad5dc1'),
'previous':('data/cache/research/old_holding_topup_research_20261002_v1/results.json','1192aa5876b8ea9e36c84ad33d88f5504df849e8612312f1886fad6b579351fb'),
'previous_publication':('data/cache/research/old_holding_topup_research_20261002_v1/publication.json','ed4f230d5e74ac0fb2000149caab80825e48d36cf3d7cd98a5f0858abc0fbc16'),
'previous_audit':('DYNAMIC_OLD_HOLDING_TOPUP_INDEPENDENT_READBACK_20261002.md','40f02f234a2661b0c3e0bb0ed2e7456a038d664c2e0e631561826f7b1e57f9ec')}
PRODUCER=ROOT/'scripts/ndx_cash_topup_neighbor_preparation_20261003.py'
PRODUCER_SHA='cb7f801f0d36f24163768ce41e8994398e0a223b879eb825276e486ee7e8e5bc'
CORE=ROOT/'backtest/ndx_cash_topup_neighbor_preparation_research.py'
CORE_SHA='66e7f8eb66d6a399fe91064e0661a311f7a194a6c7dcc89cb41f0a3b9763ff73'
RULE='ALL_SAVED_FEASIBLE_SEEDS_SINGLE_PM1_AND_PAIR_PM1_NONNEGATIVE_SAVED_CAPS_V1'
TASK_FALSE=('risk_evaluated','financial_feasibility_evaluated','issuer_eligibility_verified','old_evaluations_repeated','fit_performed','account_executed','orders_executed','point_in_time_verified','promotion_allowed','global_optimality_claimed','full_integer_domain_exhausted','target_weights_changed','holdings_sold','new_candidates_selected')
OUT_FALSE=('risk_evaluated','financial_feasibility_evaluated','old_search_reexecuted','old_audit_reexecuted','fit_performed','account_executed','orders_executed','point_in_time_verified','promotion_allowed','full_transitive_source_closure_reverified','full_integer_domain_exhausted','economic_winner_selected')
def require(ok,msg):
    if not ok:raise ValueError(msg)
def enc(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(b):return hashlib.sha256(b).hexdigest()
def digest(v):return sha(enc(v))
def exact(a,b,msg):require(enc(a)==enc(b),msg)
def decode(raw):
    def pairs(items):
        out={}
        for k,v in items:require(k not in out,'Duplicate JSON key');out[k]=v
        return out
    def fail(value):raise ValueError('Nonfinite JSON')
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=fail)
def false(obj,keys):
    for key in keys:require(obj[key] is False,'Authority/type '+key)
def integer(v):return type(v) is int and v>=0

def reconstruct_contract(input_row,previous,input_ref,previous_ref):
    exact(previous['input_row'],input_row,'Original row preserved');exact(previous['input_reference'],input_ref,'Original input reference')
    require(input_row['branch_role']=='MAIN_LANE' and previous['scenario_id']==input_row['scenario_id'],'Scenario binding')
    for o in (input_row,previous):false(o,('point_in_time_verified','promotion_allowed','fork_executable','orders_executed'))
    false(previous,('target_weights_changed','cash_must_be_fully_invested'));require(previous['new_buy_domain_is_research_assumption'] is True,'Domain conditional')
    domain=previous['domain'];ids=domain['conditional_research_buy_ids'];caps=domain['buy_limits']
    require(ids==sorted(set(ids)) and ids and set(caps)==set(ids) and all(integer(v) for v in caps.values()),'Exact domain/caps')
    require(all(integer(q) for q in input_row['holdings'].values()),'Original integer holdings')
    require(set(ids)==set(input_row['target_weights'])|{s for s,q in input_row['holdings'].items() if q>0},'Complete target/old union')
    require(set(ids)<=set(input_row['securities']) and set(ids)<=set(input_row['execution_prices']),'Original quotes and metadata')
    exact(previous['original_allowed_buy_security_ids'],input_row['allowed_buy_security_ids'],'Original permissions')
    branches=previous['evaluation']['branches'];require(len(branches)==1 and branches[0]['branch_id']==input_row['scenario_id'],'Original branch')
    plans=branches[0]['evaluated_plans'];require(type(branches[0]['evaluated_count']) is int and branches[0]['evaluated_count']==len(plans),'Original entire evaluated list')
    old=[];seeds=[];seen=set()
    for i,p in enumerate(plans):
        buy=p['buy_shares'];require(set(buy)==set(ids) and all(integer(buy[s]) and buy[s]<=caps[s] for s in ids) and type(p['feasible']) is bool,'Original buys/feasibility')
        key=tuple(buy[s] for s in ids);require(key not in seen,'Original unique vectors');seen.add(key)
        old.append(dict(candidate_index=i,buy_shares=deepcopy(buy),saved_feasible=p['feasible'],reference=dict(previous_ref,json_pointer=previous_ref['json_pointer']+'/evaluation/branches/0/evaluated_plans/'+str(i))))
        if p['feasible']:seeds.append(i)
    c=dict(schema='CONDITIONAL_TOPUP_NEIGHBOR_SCENARIO_CONTRACT_V1',rule=RULE,scenario_id=input_row['scenario_id'],input_reference=deepcopy(input_ref),previous_result_reference=deepcopy(previous_ref),original_input_row=deepcopy(input_row),conditional_research_buy_ids=deepcopy(ids),saved_buy_limits=deepcopy(caps),saved_domain_assumption=previous['assumption'],original_selected_candidate_index=previous['selected_candidate_index'],old_evaluated_points=old,all_feasible_seed_indexes=seeds,move_order='SEED_ORIGINAL_INDEX;SINGLE_SORTED_SID_MINUS_PLUS;PAIR_LEXICOGRAPHIC_MINUS_PLUS_CARTESIAN',boundary_policy='REJECT_NEGATIVE_NEW_BUY_OR_ABOVE_SAVED_CAP_NO_REBUDGET',duplicate_policy='FIRST_SEED_AND_MOVE_RETAINED;COUNTS_PRESERVE_ALL_ATTEMPTS',raw_move_attempt_count=len(seeds)*2*len(ids)**2,whole_existing_holdings_preserved=True,economic_evaluation_identity_not_created=True,**dict.fromkeys(TASK_FALSE,False))
    return dict(contract=c,contract_sha256=digest(c))

def expected_tasks(prepared,stats):
    c=prepared['contract'];ids=c['conditional_research_buy_ids'];caps=c['saved_buy_limits'];points=c['old_evaluated_points'];old={tuple(p['buy_shares'][s] for s in ids) for p in points};seen=set()
    stats.update(raw_move_attempt_count=c['raw_move_attempt_count'],processed_move_count=0,boundary_rejected_count=0,old_point_excluded_count=0,duplicate_new_point_count=0,new_candidate_count=0,unprocessed_move_count=c['raw_move_attempt_count'])
    moves=[[(j,d)] for j in range(len(ids)) for d in (-1,1)]
    moves += [[(j,a),(k,b)] for j in range(len(ids)) for k in range(j+1,len(ids)) for a,b in ((-1,-1),(-1,1),(1,-1),(1,1))]
    for index in c['all_feasible_seed_indexes']:
        p=points[index]
        for change in moves:
            stats['processed_move_count']+=1;stats['unprocessed_move_count']-=1;vector=[p['buy_shares'][s] for s in ids]
            for j,d in change:vector[j]+=d
            key=tuple(vector)
            if any(v<0 or v>caps[s] for s,v in zip(ids,key)):stats['boundary_rejected_count']+=1;continue
            if key in old:stats['old_point_excluded_count']+=1;continue
            if key in seen:stats['duplicate_new_point_count']+=1;continue
            seen.add(key);ordinal=stats['new_candidate_count'];stats['new_candidate_count']+=1
            identity=dict(schema='CONDITIONAL_TOPUP_NEIGHBOR_TASK_IDENTITY_V1',rule=RULE,scenario_contract_sha256=prepared['contract_sha256'],buy_shares=dict(zip(ids,key)))
            yield dict(task_id=digest(identity),identity=identity,scenario_id=c['scenario_id'],scenario_candidate_ordinal=ordinal,first_origin=dict(seed_candidate_index=index,seed_reference=p['reference'],moves=[dict(security_id=ids[j],delta=d) for j,d in change]),evaluation_status='NOT_EVALUATED',**dict.fromkeys(TASK_FALSE,False))
    require(stats['unprocessed_move_count']==0 and sum(stats[k] for k in ('boundary_rejected_count','old_point_excluded_count','duplicate_new_point_count','new_candidate_count'))==stats['processed_move_count'],'Independent attempt partition')

def verify_shards(prepared,row,read_bytes,folder):
    exact(row['contract_sha256'],prepared['contract_sha256'],'Scenario contract hash');stats={};oracle=iter(expected_tasks(prepared,stats));offset=0
    for i,ref in enumerate(row['shards']):
        require(set(ref)=={'path','sha256','start','stop'} and type(ref['start']) is int and type(ref['stop']) is int and ref['start']==offset and 0<ref['stop']-offset<=1000,'Shard integer contiguous offsets')
        require(Path(ref['path'])==folder/f'tasks-{i:05d}.jsonl','Fixed shard path')
        raw=read_bytes(dict(path=ref['path'],sha256=ref['sha256']));require(raw.endswith(b'\n'),'Durable JSONL newline');lines=raw.splitlines();require(len(lines)==ref['stop']-offset,'Exact shard rows')
        if i<len(row['shards'])-1:require(len(lines)==1000,'Only final shard partial')
        for line in lines:
            expected=next(oracle,None);require(expected is not None,'No extra task');exact(decode(line),expected,'Independent task identity/provenance/order');require(line==enc(expected),'Canonical saved JSONL bytes')
        offset=ref['stop']
    require(next(oracle,None) is None,'Missing task/shard');exact(row['statistics'],stats,'Independent full counts')
    c=prepared['contract'];require(row['scenario_id']==c['scenario_id'],'Row scenario');exact(row['old_selected_candidate_index'],c['original_selected_candidate_index'],'Saved selected only reference')
    exact(row['old_feasible_seed_count'],len(c['all_feasible_seed_indexes']),'All feasible seeds');exact(row['old_evaluated_point_count'],len(c['old_evaluated_points']),'All previous vectors');false(row,OUT_FALSE)
    return stats

def readback(*,execute=False):
    require(type(execute) is bool and execute,'Explicit execution')
    require(type(PREPARATION_SHA) is str and type(PUBLICATION_SHA) is str,'Future actual anchors pending');require(not OUTPUT.exists(),'No independent retry')
    sources={str(SOURCE):LOADED,str(PRODUCER):PRODUCER_SHA,str(CORE):CORE_SHA}
    def read(ref):
        require(set(ref)=={'path','sha256'} and type(ref['sha256']) is str and re.fullmatch('[a-f0-9]{64}',ref['sha256']),'Exact reference')
        raw=Path(ref['path']).read_bytes();require(sha(raw)==ref['sha256'],'Consumed saved bytes');require(ref['path'] not in sources or sources[ref['path']]==ref['sha256'],'Source collision');sources[ref['path']]=ref['sha256'];return raw
    refs={k:dict(path=str(ROOT/p),sha256=h) for k,(p,h) in PARENTS.items()};docs={k:decode(read(r)) if k!='previous_audit' else read(r) for k,r in refs.items()}
    pr=dict(path=str(DIRECTORY/'preparation.json'),sha256=PREPARATION_SHA);pu=dict(path=str(DIRECTORY/'publication.json'),sha256=PUBLICATION_SHA);value=decode(read(pr));pub=decode(read(pu))
    require(value['schema']=='CASH_TOPUP_NEIGHBOR_PREPARATION_V1' and pub['schema']=='CASH_TOPUP_NEIGHBOR_PREPARATION_PUBLICATION_V1' and pub['status']=='PUBLISHED_UNEVALUATED_CANDIDATES_ONLY','Preparation receipt')
    exact(pub['preparation_reference'],pr,'External prepared reference');exact(value['input_references'],refs,'Fixed original parents')
    expected_sources={str(PRODUCER):PRODUCER_SHA,str(CORE):CORE_SHA,**{r['path']:r['sha256'] for r in refs.values()}};exact(value['source_hashes'],expected_sources,'Exact producer source closure');exact(pub['source_hashes'],expected_sources,'Publication source closure')
    false(value,OUT_FALSE);false(pub,OUT_FALSE);require(value['declared_local_neighborhood_complete'] is True and value['old_result_references_only'] is True and value['new_dated_77_pool_used'] is False,'Declared domain only');exact(value['task_evaluation_count'],0,'No evaluation')
    require(docs['inputs']['schema']=='REMAINING_STANDARD_CASH_INPUTS_V1' and len(docs['inputs']['rows'])==64 and docs['previous']['schema']=='OLD_HOLDING_TOPUP_CONDITIONAL_RESEARCH_V1' and len(docs['previous']['rows'])==40,'Complete parents')
    for role,pkey,rkey,status in [('inputs','inputs_publication','input_reference','INPUTS_ONLY_NOT_EXECUTED'),('previous','previous_publication','result_reference','PUBLISHED_CONDITIONAL_TOPUPS_ONLY')]:
        receipt=docs[pkey];exact(receipt[rkey],refs[role],'Parent receipt');exact(receipt['source_hashes'],docs[role]['source_hashes'],'Parent source claims');require(receipt['status']==status,'Parent success')
        for o in (receipt,docs[role]):false(o,('point_in_time_verified','promotion_allowed','orders_executed','fork_executable'))
        require(not (Path(refs[role]['path']).parent/'failure.json').exists(),'Failed parent')
    main=[(i,r) for i,r in enumerate(docs['inputs']['rows']) if r['branch_role']=='MAIN_LANE'];require(len(main)==40 and len({r['scenario_id'] for i,r in main})==40,'Exact40 distinct scenarios');exact(value['scenario_count'],40,'Full scenario denominator');require(len(value['rows'])==40,'All preparation rows')
    require([r['scenario_id'] for i,r in main]==[r['scenario_id'] for r in docs['previous']['rows']],'Original source order')
    def guard():
        for p,h in sources.items():require(sha(Path(p).read_bytes())==h,'Saved source drift')
    started_path=DIRECTORY/'started.json';started_raw=started_path.read_bytes();started=decode(read(dict(path=str(started_path),sha256=sha(started_raw))))
    require(started['schema']=='CASH_TOPUP_NEIGHBOR_PREPARATION_STARTED_V1','Started schema');exact(started['input_references'],refs,'Started inputs');exact(started['source_hashes'],expected_sources,'Started sources');exact(started['scenario_count'],40,'Started count');exact(started['shard_size'],1000,'Shard capacity');false(started,OUT_FALSE)
    guard();reports=[];totals={} 
    for j,((i,input_row),row) in enumerate(zip(main,value['rows'])):
        folder=DIRECTORY/f'scenario-{j:02d}';prepared=reconstruct_contract(input_row,docs['previous']['rows'][j],dict(refs['inputs'],json_pointer=f'/rows/{i}'),dict(refs['previous'],json_pointer=f'/rows/{j}'))
        require(Path(row['contract_reference']['path'])==folder/'contract.json','Fixed contract path');exact(decode(read(row['contract_reference'])),prepared,'Full independent contract')
        stats=verify_shards(prepared,row,read,folder);require({p.name for p in folder.iterdir()}=={'contract.json',*[f'tasks-{k:05d}.jsonl' for k in range(len(row['shards']))]},'Exact scenario files')
        for k,v in stats.items():totals[k]=totals.get(k,0)+v
        reports.append(dict(scenario_id=row['scenario_id'],contract_reference=row['contract_reference'],statistics=stats,shard_count=len(row['shards'])))
    exact(value['statistics'],totals,'Global independent partition');require({p.name for p in DIRECTORY.iterdir()}=={'started.json','preparation.json','publication.json',*[f'scenario-{j:02d}' for j in range(40)]},'Exact successful preparation namespace')
    guard();report=dict(schema='CASH_TOPUP_NEIGHBOR_PREPARATION_INDEPENDENT_READBACK_V1',status='PASS',preparation_reference=pr,publication_reference=pu,reader_sha256=LOADED,source_hashes=sources,scenario_count=40,rows=reports,statistics=totals,producer_called=False,old_audit_called=False,started_bytes_externally_anchored=False,scope='UNEVALUATED_DECLARED_LOCAL_NEIGHBORHOOD_COMPLETENESS_ONLY',**dict.fromkeys(OUT_FALSE,False))
    OUTPUT.mkdir(parents=True,exist_ok=False)
    def save(path,obj):
        b=enc(obj)
        with path.open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
        return dict(path=str(path),sha256=sha(b))
    try:
        ref=save(OUTPUT/'independent_readback.json',report);guard();require(Path(ref['path']).read_bytes()==enc(report) and {p.name for p in OUTPUT.iterdir()}=={'independent_readback.json'},'Report durable exact');return ref
    except Exception as e:save(OUTPUT/'failure.json',dict(status='FAILED_DO_NOT_CONSUME',error=str(e),retry_allowed=False));raise
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');print(json.dumps(readback(execute=p.parse_args().execute)))
