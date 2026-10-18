"""One explicit new-window combination, three task inputs, no fitter invocation."""
import argparse
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

OUTPUT=BASE/'new_cutoff_bounded_materialization_20260924_v1/materialized.json'
BOUND={
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


def build():
    require(BOUND['plan'][1] is not None,'Actual reviewed20 plan anchor pending')
    sources=dict(LOADED);guard(sources);documents={}
    for role in BOUND:
        reference=ref(role);raw=Path(reference['path']).read_bytes()
        require(codec.sha(raw)==reference['sha256'],'Consumed source bytes differ')
        documents[role]=codec.loads(raw);sources[reference['path']]=reference['sha256']
    numerical=fitter._sources();arguments=inputs(documents,numerical)
    for mapping in (materializer.LOADED,materializer.planning.LOADED,materializer.planning.bounds._LOADED,codec.LOADED,numerical,documents['plan']['source_hashes']):
        for path,digest in mapping.items():
            require(path not in sources or sources[path]==digest,'Conflicting source reference');sources[path]=digest
    guard(sources);value=materializer.materialize_slice(**arguments);guard(sources)
    require(value['combination_count']==1 and value['materialized_task_count']==3 and value['completed_task_count']==0,'One combination/three unattempted tasks required')
    return dict(schema='SOURCE_BOUND_NEW_CUTOFF_BOUNDED_MATERIALIZATION_V1',scope='CONDITIONAL_RESEARCH_TASK_INPUTS_NOT_EXECUTION',
        materialization=value,input_references={role:ref(role) for role in BOUND},source_hashes=sources,
        selected_slice_reason='FIRST_LEXICOGRAPHIC_COMBINATION_OF_FIRST_NONEXCLUDED_K_FOR_INTERFACE_VALIDATION_NOT_SCORE_SELECTION',
        external_direct_source_bytes_verified=True,materializer_invocation_count=1,combination_enumeration_performed=True,
        enumerated_combination_count=1,actual_fitter_invocation_count=0,**dict.fromkeys(FALSE,False))


def publish():
    require(not OUTPUT.parent.exists(),'Fresh fixed namespace required')
    value=build();guard(value['source_hashes']);raw=codec.pretty(value)
    OUTPUT.parent.mkdir(parents=True,exist_ok=False)
    with OUTPUT.open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
    guard(value['source_hashes']);require(OUTPUT.read_bytes()==raw,'Published bytes differ')
    require({path.name for path in OUTPUT.parent.iterdir()}=={'materialized.json'},'Unexpected namespace file')
    return dict(path=str(OUTPUT),sha256=codec.sha(raw))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--publish',action='store_true');args=parser.parse_args()
    require(args.publish,'Explicit --publish required');print(json.dumps(publish()))
