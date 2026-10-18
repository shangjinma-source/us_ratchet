"""Create-only 40-scenario incremental candidate preparation; no evaluation."""
import argparse,hashlib,json,os,types
from pathlib import Path
SOURCE=Path(__file__).resolve();ROOT=SOURCE.parents[1];LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
CORE=ROOT/'backtest/ndx_cash_topup_neighbor_preparation_research.py';CORE_SHA='66e7f8eb66d6a399fe91064e0661a311f7a194a6c7dcc89cb41f0a3b9763ff73'
OUTPUT=ROOT/'data/cache/research/cash_topup_neighbor_preparation_20261003_v1';SHARD_SIZE=1000
BOUND={
 'inputs':('data/cache/research/remaining_standard_cash_inputs_20261002_v1/inputs.json','1143482cc4d610c6bd3976f846730b98ef1f11148e3b1f5eb008135a5faea1e5'),
 'inputs_publication':('data/cache/research/remaining_standard_cash_inputs_20261002_v1/publication.json','54d6f6d2771dc4caf85c07b2b8a28e33e1a50a3aace1df99308c012ae1ad5dc1'),
 'previous':('data/cache/research/old_holding_topup_research_20261002_v1/results.json','1192aa5876b8ea9e36c84ad33d88f5504df849e8612312f1886fad6b579351fb'),
 'previous_publication':('data/cache/research/old_holding_topup_research_20261002_v1/publication.json','ed4f230d5e74ac0fb2000149caab80825e48d36cf3d7cd98a5f0858abc0fbc16'),
 'previous_audit':('DYNAMIC_OLD_HOLDING_TOPUP_INDEPENDENT_READBACK_20261002.md','40f02f234a2661b0c3e0bb0ed2e7456a038d664c2e0e631561826f7b1e57f9ec')}
FLAGS=dict.fromkeys(('risk_evaluated','financial_feasibility_evaluated','old_search_reexecuted','old_audit_reexecuted','fit_performed','account_executed','orders_executed','point_in_time_verified','promotion_allowed','full_transitive_source_closure_reverified','full_integer_domain_exhausted','economic_winner_selected'),False)
def require(ok,msg):
    if not ok:raise ValueError(msg)
def enc(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(b):return hashlib.sha256(b).hexdigest()
def exact(a,b,msg):require(enc(a)==enc(b),msg)
def refs():return {k:dict(path=str(ROOT/p),sha256=h) for k,(p,h) in BOUND.items()}
def guard(sources):
    for p,h in ((str(SOURCE),LOADED),(str(CORE),CORE_SHA)):require(p not in sources or sources[p]==h,'Source conflict')
    for p,h in {**sources,str(SOURCE):LOADED,str(CORE):CORE_SHA}.items():require(sha(Path(p).read_bytes())==h,'Source drift')
def decode(b):
    def pairs(items):
        out={}
        for k,v in items:require(k not in out,'Duplicate key');out[k]=v
        return out
    def invalid(v):raise ValueError('Nonfinite JSON')
    return json.loads(b,object_pairs_hook=pairs,parse_constant=invalid)
def save(path,v):
    b=enc(v)
    with path.open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
    require(path.read_bytes()==b,'Saved bytes');return dict(path=str(path),sha256=sha(b))
def validate_inputs(docs,references):
    require(docs['inputs']['schema']=='REMAINING_STANDARD_CASH_INPUTS_V1' and docs['previous']['schema']=='OLD_HOLDING_TOPUP_CONDITIONAL_RESEARCH_V1','Sealed schemas')
    require(len(docs['inputs']['rows'])==64 and len(docs['previous']['rows'])==40,'Complete old scope')
    for role,pubkey,refkey in [('inputs','inputs_publication','input_reference'),('previous','previous_publication','result_reference')]:
        exact(docs[pubkey][refkey],references[role],'Published source');exact(docs[pubkey]['source_hashes'],docs[role]['source_hashes'],'Source map')
        for obj in (docs[role],docs[pubkey]):
            for k in ('point_in_time_verified','promotion_allowed','orders_executed','fork_executable'):require(obj[k] is False,'Conditional parent flags')
    require(docs['previous_publication']['status']=='PUBLISHED_CONDITIONAL_TOPUPS_ONLY','Previous success')
    require(docs['inputs_publication']['status']=='INPUTS_ONLY_NOT_EXECUTED','Input publication role')
    main=[(i,r) for i,r in enumerate(docs['inputs']['rows']) if r['branch_role']=='MAIN_LANE'];require(len(main)==40,'Complete main rows')
    require(len({r['scenario_id'] for i,r in main})==40 and [r['scenario_id'] for i,r in main]==[r['scenario_id'] for r in docs['previous']['rows']],'Original40 order')
    require({r['lane'] for i,r in main}=={'RETURN','BAD_TAIL','DRAWDOWN','LEGACY_TARGET_DISTANCE'} and {r['cash_event']['amount_usd'] for i,r in main}=={'1000','10000'},'Original lanes and research amounts')
    return main
def load():
    r=refs();sources={str(SOURCE):LOADED,str(CORE):CORE_SHA};guard(sources);docs={}
    for role,ref in r.items():
        b=Path(ref['path']).read_bytes();require(sha(b)==ref['sha256'],'Consumed bytes');sources[ref['path']]=ref['sha256']
        if role!='previous_audit':docs[role]=decode(b)
    for role in ('inputs','previous'):require(not (Path(r[role]['path']).parent/'failure.json').exists(),'Failed parent')
    main=validate_inputs(docs,r);blob=CORE.read_bytes();require(sha(blob)==CORE_SHA,'Fresh core');core=types.ModuleType('_fresh_neighbor_prepare');exec(compile(blob,str(CORE),'exec'),core.__dict__);guard(sources)
    return docs,r,sources,main,core
def write_scenario(prepared,core,folder):
    folder.mkdir(exist_ok=False);contractref=save(folder/'contract.json',prepared);stats={};shards=[];buffer=[];start=0
    def flush():
        nonlocal buffer,start
        if not buffer:return
        p=folder/('tasks-'+str(len(shards)).zfill(5)+'.jsonl');b=b''.join(enc(row)+b'\n' for row in buffer)
        with p.open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
        require(p.read_bytes()==b,'Shard durable bytes');shards.append(dict(path=str(p),sha256=sha(b),start=start,stop=start+len(buffer)));start+=len(buffer);buffer=[]
    for task in core.iter_neighbors(prepared,stats):
        buffer.append(task)
        if len(buffer)==SHARD_SIZE:flush()
    flush();return dict(scenario_id=prepared['contract']['scenario_id'],contract_reference=contractref,contract_sha256=prepared['contract_sha256'],statistics=stats,shards=shards,old_selected_candidate_index=prepared['contract']['original_selected_candidate_index'],old_feasible_seed_count=len(prepared['contract']['all_feasible_seed_indexes']),old_evaluated_point_count=len(prepared['contract']['old_evaluated_points']),**FLAGS)
def run(*,execute=False):
    require(execute is True and not OUTPUT.exists(),'Explicit unique preparation only');docs,r,sources,main,core=load();OUTPUT.mkdir(parents=True,exist_ok=False)
    try:
        save(OUTPUT/'started.json',dict(schema='CASH_TOPUP_NEIGHBOR_PREPARATION_STARTED_V1',input_references=r,source_hashes=sources,scenario_count=40,shard_size=SHARD_SIZE,**FLAGS));rows=[]
        for j,(i,row) in enumerate(main):
            guard(sources);prepared=core.prepare_scenario(input_row=row,previous_row=docs['previous']['rows'][j],input_reference=dict(r['inputs'],json_pointer='/rows/'+str(i)),previous_reference=dict(r['previous'],json_pointer='/rows/'+str(j)))
            rows.append(write_scenario(prepared,core,OUTPUT/('scenario-'+str(j).zfill(2))))
        guard(sources);counts={k:sum(row['statistics'][k] for row in rows) for k in rows[0]['statistics']}
        out=save(OUTPUT/'preparation.json',dict(schema='CASH_TOPUP_NEIGHBOR_PREPARATION_V1',rows=rows,scenario_count=40,statistics=counts,declared_local_neighborhood_complete=counts['unprocessed_move_count']==0,task_evaluation_count=0,input_references=r,source_hashes=sources,old_result_references_only=True,new_dated_77_pool_used=False,**FLAGS));guard(sources)
        pub=save(OUTPUT/'publication.json',dict(schema='CASH_TOPUP_NEIGHBOR_PREPARATION_PUBLICATION_V1',status='PUBLISHED_UNEVALUATED_CANDIDATES_ONLY',preparation_reference=out,source_hashes=sources,**FLAGS));guard(sources)
        for ref in (out,pub):require(sha(Path(ref['path']).read_bytes())==ref['sha256'],'Final publication bytes')
        return out
    except Exception as e:save(OUTPUT/'failure.json',dict(status='FAILED_DO_NOT_RETRY_OR_CONSUME',error_type=type(e).__name__,error=str(e),**FLAGS));raise
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');print(json.dumps(run(execute=p.parse_args().execute)))
