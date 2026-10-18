"""Fixed first-two CTAS-containing prefixes per k; no score selection or fitting."""
import argparse
from copy import deepcopy
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import sys
SOURCE=Path(__file__).resolve();ROOT=SOURCE.parents[1];BASE=ROOT/'data/cache/research'
sys.path.insert(0,str(ROOT))
from backtest import ndx_issuer_task_materialization_research as materializer
from scripts import ndx_new_cutoff_typed_panel_independent_readback_20260923 as codec
OUTPUT=BASE/'new_cutoff_ctas_combination_materialization_20260925_v1/queue.json'
FORCED_SID='security:0000723254:172908105'
BOUND={
 'plan':('new_cutoff_shard_prepare_20260925_v6/plan.json','c18b54c1f1aa41f7833f0b88a8fa7270b3eb0bc7c8ea0cebb0628c3645a78dd9'),
 'panel':('new_cutoff_conditional_panel_20260925_v6/panel.json','d5feacbfbe85d38fd8c66aef9dc30686316cfd1c7ccaf4eafb58cc8c5e26e269'),
 'audit':('new_cutoff_conditional_panel_20260925_v6/independent_increment_readback.json','6229a3655bb4d73c9d113d941f9dbec149da047c113be92193559cf5dbbd0717'),
 'rebinding':('new_cutoff_v6_completed_task_rebinding_20260925_v1/rebinding.json','9475fc1934fdf55b5c516e27f0b0291f71e4725de083ddf8b24fe930fde79704'),
 'rebinding_audit':('new_cutoff_v6_completed_task_rebinding_20260925_v1/independent_readback.json','74e5eca422a9f603da2add31c1ea0dfe6e29aee1306728a8e36e3d327d29fa09')}
PINS={str(Path(materializer.__file__).resolve()):'11348bd4aa99b8ee61bacdd12438aaf3c600e1f808e430130464895c22a2df88',str(Path(codec.__file__).resolve()):'0b5fbb5ae38a91e7919c16b9846bf165b72c7b2aae89f281125ee23ad18fe3f9'}
LOADED={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in PINS};LOADED[str(SOURCE)]=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
FALSE=('fit_performed','old_plan_build_called','panel_audit_repeated','old_completed_tasks_rematerialized','old_task_readbacks_repeated','score_filtering_performed',
 'legal_training_input_admitted','point_in_time_verified','promotion_allowed','execution_authorized','full_transitive_source_closure_reverified','full_shard_completed','all_plan_tasks_completed')

def require(ok,message):
    if not ok:raise ValueError(message)


def ref(role):return dict(path=str(BASE/BOUND[role][0]),sha256=BOUND[role][1])


def guard(sources):
    require(all(LOADED[path]==digest for path,digest in PINS.items()),'Loaded implementation differs')
    require(all(path not in sources or sources[path]==digest for path,digest in LOADED.items()),'Loaded source conflict')
    for path,digest in {**sources,**LOADED}.items():
        require(codec.sha(Path(path).read_bytes())==digest,'Source drift: '+path)


def forced_prefixes(groups,forced_sid,k,limit=2):
    """Unrank within forced-SID subset using suffix counts; never scan full ranks."""
    index=materializer.indexing.IssuerCombinationIndex(groups)
    canonical=list(zip(index.issuer_ids,index.security_groups));n=len(canonical)
    require(type(k) is int and 1<=k<=n and type(limit) is int and 1<=limit<=2,'Explicit bounded cardinality/limit')
    matches=[i for i,(_,sids) in enumerate(canonical) if forced_sid in sids];require(len(matches)==1,'Unique forced SID required');forced_i=matches[0]
    @lru_cache(None)
    def count(i,r,need):
        if r==0:return int(not need)
        if i==n or r<0 or n-i<r or (need and i>forced_i):return 0
        total=count(i+1,r,need)
        for sid in canonical[i][1]:total+=count(i+1,r-1,need and sid!=forced_sid)
        return total
    total=count(0,k,True);require(total>=limit,'Not enough forced combinations')
    results=[]
    for position in range(limit):
        residual=position;start=0;remaining=k;need=True;selection=[]
        while remaining:
            chosen=False
            for i in range(start,n):
                for sid in canonical[i][1]:
                    block=count(i+1,remaining-1,need and sid!=forced_sid)
                    if residual>=block:residual-=block;continue
                    selection.append(sid);start=i+1;remaining-=1;need=need and sid!=forced_sid;chosen=True;break
                if chosen:break
            require(chosen,'Forced unrank failed')
        require(not need and residual==0,'Forced selection invariant')
        results.append(dict(k=k,forced_local_rank=position,prefix_security_ids=selection,full_rank=index.rank(k,selection)))
    return total,results


def inputs(documents):
    outer=documents['plan'];candidate=documents['panel'];audit=documents['audit'];rebound=documents['rebinding'];readback=documents['rebinding_audit']
    require(outer['schema']=='SOURCE_BOUND_NEW_CUTOFF_SHARD_PREPARE_V6' and outer['input_references']['panel']==ref('panel') and outer['input_references']['audit']==ref('audit'),'V6 plan lineage')
    require(audit['status']=='PASSED' and audit['candidate_reference']==ref('panel') and audit['panel_content_sha256']==candidate['panel']['panel_content_sha256'],'V6 saved panel audit')
    require(rebound['schema']=='NEW_CUTOFF_V6_COMPLETED_TASK_REBINDING_V1' and rebound['input_references']['plan']==ref('plan') and
        readback['status']=='PASSED' and readback['candidate_reference']==ref('rebinding') and readback['numerical_contracts_unchanged'] is True,'Audited old402 rebinding')
    ids=[r['numerical_task_id'] for r in rebound['rows']]
    require(len(ids)==len(set(ids))==402 and ids==readback['verified_numerical_task_ids'],'Exact old402 identity set')
    require(all(d[key] is False for d in documents.values() for key in ('promotion_allowed','execution_authorized','legal_training_input_admitted','point_in_time_verified')),'Authority upgrade')
    panel=codec.decode_frames(candidate['panel']);plan=outer['plan'];ctx=plan['context']
    require(panel['schema']=='LATEST_CONDITIONAL_TYPED_PANEL_V6' and panel['conditional_security_count']==24 and panel['conditional_issuer_count']==23 and
        ctx['previous_target_weights'] is None and len(plan['fitter_source_hashes'])==25,'Full panel/prior/source contract')
    require(type(plan['planned_canonical_task_count']) is int and plan['planned_canonical_task_count']==37740237,'Complete V6 task denominator')
    require(ctx['weight_specs']==['equal_weight','constrained_fixed_shrinkage','constrained_fixed_shrinkage_turnover_anchor'],'No specification alias')
    projection=dict(panel_reference=ref('panel'),panel_content_sha256=panel['panel_content_sha256'],dates=[d.date().isoformat() for d in panel['returns'].index],
        columns=panel['returns'].columns.tolist(),returns=panel['returns'].values.tolist(),universe=[{key:r[key] for key in ('security_id','ticker','issuer_id','risk_chain')} for r in panel['universe'].to_dict('records')])
    require(any(r['security_id']==FORCED_SID and r['ticker']=='CTAS' and r['risk_chain']=='industrial' for r in projection['universe']),'Explicit CTAS coordinate')
    groups=[(r['issuer_id'],r['security_ids']) for r in plan['canonical_groups']]
    return plan,projection,groups,ids


def prepare_arguments(plan,panel,groups):
    arguments=[];selections=[];denominators=[]
    for k in range(4,21):
        total,chosen=forced_prefixes(groups,FORCED_SID,k)
        denominators.append(dict(k=k,forced_combination_count=total))
        require(not plan['cardinalities'][k-1]['necessary_bound_certificates'],'Original necessary bound excludes requested k')
        for selection in chosen:
            rank=selection['full_rank'];shards=[s for s in plan['shards'] if s['k']==k and s['start']<=rank<s['stop']]
            require(len(shards)==1,'Unique complete-pool shard')
            selection['shard_id']=shards[0]['shard_id'];selections.append(selection)
            arguments.append(dict(plan=plan,plan_reference=ref('plan'),shard_id=shards[0]['shard_id'],panel=panel,start=rank,stop=rank+1,max_materialized_combinations=1))
    require(sum(r['forced_combination_count'] for r in denominators)==6290694,'Complete CTAS denominator')
    return arguments,selections,denominators


def materialize_new(arguments,selections,old_ids):
    require(len(arguments)==len(selections)==34 and len(set(old_ids))==402,'Exact bounded input coverage')
    seen=set(old_ids);values=[]
    for argument,selection in zip(arguments,selections):
        value=materializer.materialize_slice(**argument)
        require(type(value['combination_count']) is int and value['combination_count']==1 and type(value['materialized_task_count']) is int and value['materialized_task_count']==3 and
            type(value['completed_task_count']) is int and value['completed_task_count']==0,'One new unattempted combination')
        combination=value['combinations'][0]
        require(combination['prefix_security_ids']==selection['prefix_security_ids'] and combination['rank']==selection['full_rank'] and FORCED_SID in combination['prefix_security_ids'],'Saved fullpool rank and required SID')
        for task in combination['tasks']:
            require(task['numerical_task_id'] not in seen,'Completed or duplicate numerical identity cannot be materialized');seen.add(task['numerical_task_id'])
        values.append(value)
    require(len(seen)==504,'402external plus102new task identities')
    return values


def merge(target,mapping):
    for p,h in mapping.items():require(p not in target or target[p]==h,'Source conflict');target[p]=h


def build():
    require(all(type(h) is str and len(h)==64 for p,h in BOUND.values()),'Actual V6 rebinding and independent readback anchors pending')
    sources=dict(LOADED);guard(sources);documents={}
    for role in BOUND:
        r=ref(role);blob=Path(r['path']).read_bytes();require(codec.sha(blob)==r['sha256'],'Hard input hash');documents[role]=codec.loads(blob);sources[r['path']]=r['sha256']
    plan,panel,groups,old_ids=inputs(documents)
    for mapping in (materializer.LOADED,materializer.planning.LOADED,materializer.planning.bounds._LOADED,codec.LOADED,plan['fitter_source_hashes'],documents['plan']['source_hashes']):merge(sources,mapping)
    guard(sources);arguments,selections,denominators=prepare_arguments(plan,panel,groups)
    values=materialize_new(arguments,selections,old_ids);guard(sources)
    return dict(schema='NEW_CUTOFF_CTAS_COMBINATION_MATERIALIZATION_V1',input_references={k:ref(k) for k in BOUND},source_hashes=sources,
        selections=selections,new_materializations=values,forced_sid=FORCED_SID,forced_combination_counts=denominators,
        selection_rule='FIRST_TWO_FORCED_CTAS_PREFIX_COMBINATIONS_PER_K4_TO20_NO_SCORE_SELECTION',
        reused_completed_reference=dict(rebinding_reference=ref('rebinding'),independent_readback_reference=ref('rebinding_audit'),numerical_task_ids=old_ids),
        new_combination_count=34,new_task_count=102,new_completed_task_count=0,external_completed_task_count=402,full_plan_task_denominator=37740237,
        remaining_uncompleted_plan_task_count=37739835,complete_cardinalities=deepcopy(plan['cardinalities']),materializer_invocation_count=34,actual_fitter_invocation_count=0,
        complete_observed_provenance_and_missing=deepcopy(documents['plan']['complete_observed_provenance_and_missing']),
        preserved_sidecar_references=[deepcopy(documents['plan'][key]) for key in ('preserved_evidence_sidecar_reference','preserved_incremental_evidence_sidecar_reference','preserved_v3_incremental_evidence_sidecar_reference','preserved_v4_incremental_evidence_sidecar_reference','preserved_v5_incremental_evidence_sidecar_reference','preserved_v6_incremental_evidence_sidecar_reference')],
        **dict.fromkeys(FALSE,False))


def publish():
    require(not OUTPUT.parent.exists(),'Fresh fixed namespace required')
    value=build();guard(value['source_hashes']);blob=codec.pretty(value);OUTPUT.parent.mkdir(parents=True,exist_ok=False)
    with OUTPUT.open('xb') as stream:stream.write(blob);stream.flush();os.fsync(stream.fileno())
    guard(value['source_hashes']);require(OUTPUT.read_bytes()==blob and {p.name for p in OUTPUT.parent.iterdir()}=={'queue.json'},'Output bytes/namespace drift')
    return dict(path=str(OUTPUT),sha256=codec.sha(blob))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--publish',action='store_true');args=parser.parse_args();require(args.publish,'Explicit publish required');print(json.dumps(publish()))


