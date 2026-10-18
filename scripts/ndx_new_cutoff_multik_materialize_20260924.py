"""Fixed multi-k prefix batch, with completed first combination referenced only."""
import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys

SOURCE=Path(__file__).resolve();ROOT=SOURCE.parents[1];BASE=ROOT/'data/cache/research'
sys.path.insert(0,str(ROOT))
from backtest import ndx_issuer_task_materialization_research as materializer
from backtest import ndx_dynamic_cutoff_refit_v2_research as fitter
from scripts import ndx_new_cutoff_typed_panel_independent_readback_20260923 as codec

OUTPUT=BASE/'new_cutoff_multik_materialization_20260924_v1/queue.json'
BOUND={
 'completed_index':('new_cutoff_completed_task_index_20260924_v1/index.json','bd104f712a006d9427384929718a49bf6b229ed1b3dc2a3fdc227a8d40a3c369'),
 'old_materialized':('new_cutoff_bounded_materialization_20260924_v1/materialized.json','ce8b3c7545b8123c63eeabd0db138c11689d4d535643e58bde720b5a955fc9e0'),
 'old_materialization_audit':('new_cutoff_bounded_materialization_20260924_v1/independent_materialization_readback.json','a2c996e2f681ad959d0290de2592093e25c31ddfa458d5012713f009b402e8dc'),
 'plan':('new_cutoff_shard_prepare_20260924_v2/plan.json','50b3c661325bc4c2c4337cdb3d520413aa51f4dc94a869af9f94fdbd5bb0bceb'),
 'panel':('new_cutoff_conditional_panel_20260924_v2/panel.json','6dcd97bd87dfabab272dc50f9ac7d06e11410e1bf63d305596317236a348d412'),
 'audit':('new_cutoff_conditional_panel_20260924_v2/independent_increment_readback.json','975fc921977a1295cc70f6d3b0a9eda0e4ac7864895a76551f815ab89888b283'),
 'old_plan_metadata':('latest_conditional_all_k_refit_20260919_v1/plan.json','7b9cd1fd9dbbc9c42625495e73803e633a81f86039e1e1113ba9de3d295c52f0'),
}
PINS={str(Path(materializer.__file__).resolve()):'11348bd4aa99b8ee61bacdd12438aaf3c600e1f808e430130464895c22a2df88',
 str(Path(fitter.__file__).resolve()):'4bb005b7f88a1e806fc25dede38b0f15c42187c2aa6024d3eb32155d64abab75',
 str(Path(codec.__file__).resolve()):'0b5fbb5ae38a91e7919c16b9846bf165b72c7b2aae89f281125ee23ad18fe3f9'}
LOADED={path:hashlib.sha256(Path(path).read_bytes()).hexdigest() for path in PINS}
LOADED[str(SOURCE)]=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
FALSE=('fit_performed','old_fit_results_reused','old_plan_build_called','panel_audit_repeated','winner_selected',
 'complete_ndx_eligible_pool_verified','legal_training_input_admitted','point_in_time_verified','promotion_allowed',
 'execution_authorized','full_transitive_source_closure_reverified','full_shard_completed','all_plan_tasks_completed')


def require(ok,message):
    if not ok:raise ValueError(message)


def ref(role):return dict(path=str(BASE/BOUND[role][0]),sha256=BOUND[role][1])


def guard(sources):
    require(all(LOADED[path]==digest for path,digest in PINS.items()),'Loaded implementation differs')
    require(all(path not in sources or sources[path]==digest for path,digest in LOADED.items()),'Loaded source conflict')
    for path,digest in {**sources,**LOADED}.items():
        require(codec.sha(Path(path).read_bytes())==digest,'Source drift: '+path)


def inputs(documents,numerical):
    outer,candidate,audit,old=(documents[key] for key in ('plan','panel','audit','old_plan_metadata'))
    require(outer['schema']=='SOURCE_BOUND_NEW_CUTOFF_SHARD_PREPARE_V2' and outer['input_references']['panel']==ref('panel') and
        outer['input_references']['audit']==ref('audit'),'Exact source-bound plan lineage')
    require(all(outer[key] is False for key in ('fit_performed','combination_enumeration_performed','task_inputs_materialized',
        'execution_authorized','point_in_time_verified','legal_training_input_admitted','promotion_allowed')),'Plan operation scope differs')
    require(candidate['schema']=='NEW_CUTOFF_CONDITIONAL_TYPED_PANEL_DOCUMENT_V2' and
        audit['schema']=='NEW_CUTOFF_TYPED_PANEL_INCREMENT_INDEPENDENT_READBACK_V2' and audit['status']=='PASSED','V2 audited panel required')
    require(audit['candidate_reference']==ref('panel') and audit['producer_reference']==dict(
        path=str(ROOT/'scripts/ndx_new_cutoff_conditional_panel_v2_20260924.py'),
        sha256='a7a815c179e39de7678f1cb90da7488ee0157e8de636d768ac96f01b03f1f9b1'),'Audited parent differs')
    require(type(audit['increment_reconstruction_count']) is int and audit['increment_reconstruction_count']==1 and
        audit['independently_recomputed_tickers']==['PCAR'] and all(audit[key] is True for key in
        ('original_nineteen_five_frames_exact','unchanged_other99_gaps_exact','full_original101_and_incremental_sidecars_compared','typed_roundtrip_exact')),'Complete increment audit required')
    require(all(document[key] is False for document in (candidate,audit) for key in
        ('fit_performed','point_in_time_verified','legal_training_input_admitted','promotion_allowed','execution_authorized')),'Source authority changed')
    panel=codec.decode_frames(candidate['panel'])
    require(panel['schema']=='LATEST_CONDITIONAL_TYPED_PANEL_V2' and all(panel[key] is False for key in codec.PANEL_FALSE),'Explicit conditional V2 panel')
    require(panel['cutoff']=='2026-09-21' and panel['conditional_security_count']==outer['conditional_security_count']==audit['conditional_security_count']==20 and
        panel['conditional_issuer_count']==outer['conditional_issuer_count']==audit['conditional_issuer_count']==19,'Actual20/19 denominator')
    require(panel['panel_content_sha256']==outer['panel_content_sha256']==audit['panel_content_sha256'] and
        {name:list(panel[name].shape) for name in codec.FRAMES}==audit['frame_shapes'],'Audited typed checksum/shape differs')
    require(panel['observed_security_count']==101 and panel['observed_issuer_count']==100 and
        len(panel['observed_provenance_and_missing'])==101 and len(candidate['original_evidence_and_projection'])==101 and
        len(candidate['incremental_evidence_and_projection'])==2,'Complete observed evidence denominator')
    plan=outer['plan'];context=plan['context']
    require(context['panel_reference']==ref('panel') and context['panel_audit_reference']==ref('audit') and
        context['decision_cutoff']==panel['cutoff'] and context['previous_target_weights'] is None,'First decision source context required')
    require(old['schema']=='LATEST_CONDITIONAL_ALL_K_REFIT_PLAN_V1' and old['cutoff']=='2026-09-17' and len(numerical)==25 and
        numerical.get(str(Path(fitter.__file__).resolve()))==PINS[str(Path(fitter.__file__).resolve())] and
        all(old['historical_expected_source_hashes'].get(path)==digest for path,digest in numerical.items()) and
        plan['fitter_source_hashes']==numerical,'Original numerical closure differs')
    require(bool(old['canonical_tasks']) and all(codec.canonical(task['parameters'])==codec.canonical(context['parameters']) for task in old['canonical_tasks']),
        'Original parameter metadata differs')
    require(plan['cardinalities'][3]['k']==4 and not plan['cardinalities'][3]['necessary_bound_certificates'] and
        all(card['necessary_bound_certificates'] for card in plan['cardinalities'][:3]),'First nonexcluded cardinality differs')
    matches=[shard for shard in plan['shards'] if shard['k']==4 and shard['start']==0]
    require(len(matches)==1,'Unique first k4 interval required')
    projection=dict(panel_reference=ref('panel'),panel_content_sha256=panel['panel_content_sha256'],
        dates=[value.date().isoformat() for value in panel['returns'].index],columns=panel['returns'].columns.tolist(),
        returns=panel['returns'].values.tolist(),universe=[{key:row[key] for key in ('security_id','ticker','issuer_id','risk_chain')}
        for row in panel['universe'].to_dict('records')])
    return dict(plan=plan,plan_reference=ref('plan'),shard_id=matches[0]['shard_id'],panel=projection,
        start=0,stop=1,max_materialized_combinations=1)


def batch_arguments(base):
    """Count/interval metadata only; no call to slice or rank/unrank here."""
    plan=base['plan']
    require(type(plan['all_k_combination_count']) is int and plan['all_k_combination_count']==786431 and
        type(plan['necessary_bound_excluded_combination_count']) is int and plan['necessary_bound_excluded_combination_count']==1331 and
        type(plan['planned_canonical_task_count']) is int and plan['planned_canonical_task_count']==2355300,'Complete twenty-security denominator required')
    require([c['k'] for c in plan['cardinalities']]==list(range(1,20)),'All nineteen cardinalities required')
    arguments=[]
    for k in range(4,20):
        start=1 if k==4 else 0;stop=2
        card=plan['cardinalities'][k-1]
        require(not card['necessary_bound_certificates'] and card['combination_count']>=stop,'Requested prefix must be unexcluded and present')
        shards=[s for s in plan['shards'] if s['k']==k and s['start']<=start and s['stop']>=stop]
        require(len(shards)==1,'Unique containing shard required')
        arguments.append(dict(base,shard_id=shards[0]['shard_id'],start=start,stop=stop,max_materialized_combinations=stop-start))
    return arguments


def merge(target,mapping):
    for path,digest in mapping.items():
        require(path not in target or target[path]==digest,'Conflicting source reference');target[path]=digest


def completed_reference(documents):
    index=documents['completed_index'];old=documents['old_materialized'];audit=documents['old_materialization_audit']
    require(index['schema']=='NEW_CUTOFF_COMPLETED_TASK_INDEX_V1' and index['input_references']==dict(
        plan=ref('plan'),materialized=ref('old_materialized'),materialization_audit=ref('old_materialization_audit')),'Exact completion index parents')
    require(all(type(index[key]) is int and index[key]==value for key,value in dict(completed_task_count=3,completed_combination_count=1,
        completed_original_risk_pass_count=3,completed_original_risk_failure_count=0,original_plan_task_denominator=2355300,
        remaining_plan_task_count=2355297,original_plan_combination_denominator=785100,remaining_plan_combination_count=785099).items()),'Exact external completion denominator')
    require(all(index[key] is False for key in ('fit_performed','promotion_allowed','full_shard_completed','all_plan_tasks_completed')),'Completion authority upgraded')
    require(audit['status']=='PASSED' and audit['candidate_reference']==ref('old_materialized'),'Original materialization independently read back')
    combo=old['materialization']['combinations'][0]
    require(len(old['materialization']['combinations'])==1 and combo['k']==4 and combo['rank']==0 and
        index['completed_coordinate']==dict(k=4,rank=0,prefix_security_ids=combo['prefix_security_ids']),'Only original k4 rank0 external reuse')
    rows=index['completed_tasks'];tasks=combo['tasks']
    require(len(rows)==len(tasks)==3,'Exact three completed specifications')
    for position,(row,task) in enumerate(zip(rows,tasks)):
        require(row['full_task']==task and row['numerical_task_id']==task['numerical_task_id'] and row['weight_spec']==task['numerical_identity']['weight_spec'] and
            row['fit_data_sha256']==combo['fit_data_sha256'] and row['status']=='COMPLETED_EXTERNALLY_AUDITED_ORIGINAL_FIVE_RISKS_PASSED','Original full task identity differs')
        require(row['task_reference']==dict(ref('old_materialized'),json_pointer='/materialization/combinations/0/tasks/'+str(position)),'Original task pointer differs')
        equal=row['weight_spec']=='equal_weight';expected=dict(wrapper_call_attempt_count=1,deterministic_generation_request_count=int(equal),numerical_fit_request_count=int(not equal),import_count=0)
        require(codec.canonical(row['operation_counts'])==codec.canonical(expected),'Completed operation counts differ')
        for key in ('started_reference','raw_reference','postcheck_reference','independent_readback_reference'):
            r=row[key];require(set(r)=={'path','sha256'} and index['source_hashes'].get(r['path'])==r['sha256'],'Complete external evidence references required')
    return dict(completed_index_reference=ref('completed_index'),materialized_reference=ref('old_materialized'),
        materialization_audit_reference=ref('old_materialization_audit'),completed_coordinate=deepcopy(index['completed_coordinate']),
        numerical_task_ids=[row['numerical_task_id'] for row in rows],completed_tasks=deepcopy(rows))


def materialize_batch(arguments,old_task_ids):
    require(len(arguments)==16 and [(a['start'],a['stop']) for a in arguments]==[(1,2)]+[(0,2)]*15,'Exact bounded request intervals')
    values=[];seen=set(old_task_ids)
    require(len(seen)==3,'Three distinct externally completed tasks required')
    for expected_k,argument in zip(range(4,20),arguments):
        value=materializer.materialize_slice(**argument)
        require(all(type(value[key]) is int for key in ('k','combination_count','materialized_task_count','completed_task_count')) and
            value['k']==expected_k and value['combination_count']==argument['stop']-argument['start'] and
            value['materialized_task_count']==3*value['combination_count'] and value['completed_task_count']==0,'New slice counts differ')
        for combination in value['combinations']:
            require(len(combination['tasks'])==3,'Three explicit specifications required')
            for task in combination['tasks']:
                identity=task['numerical_task_id'];require(identity not in seen,'Completed or duplicate task cannot be rematerialized');seen.add(identity)
        values.append(value)
    require(len(seen)==96,'Exact external three plus new ninety-three identity coverage')
    return values


def build():
    require(all(type(pair[1]) is str and len(pair[1])==64 for pair in BOUND.values()),'Reviewed completed index anchor pending')
    sources=dict(LOADED);guard(sources);documents={}
    for role in BOUND:
        reference=ref(role);raw=Path(reference['path']).read_bytes()
        require(codec.sha(raw)==reference['sha256'],'Consumed source bytes differ')
        documents[role]=codec.loads(raw);sources[reference['path']]=reference['sha256']
    numerical=fitter._sources();base=inputs(documents,numerical);arguments=batch_arguments(base)
    reused=completed_reference(documents)
    for mapping in (materializer.LOADED,materializer.planning.LOADED,materializer.planning.bounds._LOADED,codec.LOADED,numerical,
        documents['plan']['source_hashes'],documents['completed_index']['source_hashes']):merge(sources,mapping)
    guard(sources);values=materialize_batch(arguments,reused['numerical_task_ids']);guard(sources)
    return dict(schema='SOURCE_BOUND_NEW_CUTOFF_MULTIK_MATERIALIZATION_V1',scope='CONDITIONAL_RESEARCH_BOUNDED_PREFIX_BATCH_NOT_SEARCH_SELECTION',
        new_materializations=values,reused_completed_reference=reused,input_references={role:ref(role) for role in BOUND},source_hashes=sources,
        complete_cardinalities=deepcopy(base['plan']['cardinalities']),all_k_combination_count=786431,necessary_bound_excluded_combination_count=1331,
        full_pool_planned_task_count=2355300,new_combination_count=31,new_task_count=93,externally_completed_combination_count=1,
        externally_completed_task_count=3,batch_combination_count=32,batch_task_count=96,new_completed_task_count=0,
        materializer_invocation_count=16,enumerated_combination_count=31,actual_fitter_invocation_count=0,
        selection_rule='FIRST_TWO_PREFIX_RANKS_PER_K_4_THROUGH_19_FIXED_WITHOUT_SCORES',
        complete_observed_provenance_and_missing=deepcopy(documents['plan']['complete_observed_provenance_and_missing']),
        preserved_evidence_sidecar_reference=deepcopy(documents['plan']['preserved_evidence_sidecar_reference']),
        preserved_incremental_evidence_sidecar_reference=deepcopy(documents['plan']['preserved_incremental_evidence_sidecar_reference']),
        score_filtering_performed=False,completed_combination_resliced=False,**dict.fromkeys(FALSE,False))


def publish():
    require(not OUTPUT.parent.exists(),'Fresh fixed namespace required')
    value=build();guard(value['source_hashes']);raw=codec.pretty(value)
    OUTPUT.parent.mkdir(parents=True,exist_ok=False)
    with OUTPUT.open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
    guard(value['source_hashes']);require(OUTPUT.read_bytes()==raw,'Published bytes differ')
    require({path.name for path in OUTPUT.parent.iterdir()}=={'queue.json'},'Unexpected namespace file')
    return dict(path=str(OUTPUT),sha256=codec.sha(raw))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--publish',action='store_true');args=parser.parse_args()
    require(args.publish,'Explicit --publish required');print(json.dumps(publish()))

