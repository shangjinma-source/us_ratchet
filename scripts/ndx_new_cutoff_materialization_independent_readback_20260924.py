"""Source-bound independent first-combination materialization readback; no fit imports."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backtest import ndx_issuer_materialization_independent_readback_research as reader
from scripts import ndx_new_cutoff_typed_panel_independent_readback_20260923 as codec
SOURCE=Path(__file__).resolve();BASE=ROOT/'data/cache/research'
PRODUCER=ROOT/'scripts/ndx_new_cutoff_bounded_materialize_20260924.py'
PRODUCER_SHA='6759de819110c0aceb294d0ce9e19a91546fd7df7a51b3bdd610119e51f84658'
CANDIDATE=BASE/'new_cutoff_bounded_materialization_20260924_v1/materialized.json'
CANDIDATE_SHA='ce8b3c7545b8123c63eeabd0db138c11689d4d535643e58bde720b5a955fc9e0'
OUTPUT=CANDIDATE.with_name('independent_materialization_readback.json')
BOUND={
 'plan':('new_cutoff_shard_prepare_20260924_v2/plan.json','50b3c661325bc4c2c4337cdb3d520413aa51f4dc94a869af9f94fdbd5bb0bceb'),
 'panel':('new_cutoff_conditional_panel_20260924_v2/panel.json','6dcd97bd87dfabab272dc50f9ac7d06e11410e1bf63d305596317236a348d412'),
 'audit':('new_cutoff_conditional_panel_20260924_v2/independent_increment_readback.json','975fc921977a1295cc70f6d3b0a9eda0e4ac7864895a76551f815ab89888b283'),
 'old_plan_metadata':('latest_conditional_all_k_refit_20260919_v1/plan.json','7b9cd1fd9dbbc9c42625495e73803e633a81f86039e1e1113ba9de3d295c52f0'),
}
READER_SHA='cedc4a97ad4138662df6ba95982f7432690367e9ce119a8813ad772940d6dbd1'
CODEC_SHA='0b5fbb5ae38a91e7919c16b9846bf165b72c7b2aae89f281125ee23ad18fe3f9'
LOADED={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (SOURCE,Path(reader.__file__).resolve(),Path(codec.__file__).resolve())}
FALSE=('fit_performed','old_fit_results_reused','old_plan_build_called','panel_audit_repeated','winner_selected','complete_ndx_eligible_pool_verified',
 'legal_training_input_admitted','point_in_time_verified','promotion_allowed','execution_authorized','full_transitive_source_closure_reverified','full_shard_completed','all_plan_tasks_completed')


def require(ok,message):
    if not ok:raise ValueError(message)


def ref(role):return dict(path=str(BASE/BOUND[role][0]),sha256=BOUND[role][1])


def merge(target,mapping):
    for p,h in mapping.items():
        require(p not in target or target[p]==h,'Conflicting source map');target[p]=h


def guard(sources):
    require(READER_SHA is not None and LOADED[str(Path(reader.__file__).resolve())]==READER_SHA and LOADED[str(Path(codec.__file__).resolve())]==CODEC_SHA,'Loaded reader pins')
    expected=dict(sources)
    merge(expected,LOADED);merge(expected,codec.LOADED)
    for p,h in expected.items():require(codec.sha(Path(p).read_bytes())==h,'Source drift')


def project(documents):
    outer,paneldoc,audit,old=(documents[k] for k in ('plan','panel','audit','old_plan_metadata'))
    require(outer['schema']=='SOURCE_BOUND_NEW_CUTOFF_SHARD_PREPARE_V2' and outer['input_references']['panel']==ref('panel') and outer['input_references']['audit']==ref('audit'),'Hard plan lineage')
    for key in ('fit_performed','combination_enumeration_performed','task_inputs_materialized','execution_authorized','point_in_time_verified','legal_training_input_admitted','promotion_allowed'):
        require(outer[key] is False,'Plan boundary')
    require(paneldoc['schema']=='NEW_CUTOFF_CONDITIONAL_TYPED_PANEL_DOCUMENT_V2' and audit['schema']=='NEW_CUTOFF_TYPED_PANEL_INCREMENT_INDEPENDENT_READBACK_V2' and audit['status']=='PASSED' and audit['candidate_reference']==ref('panel'),'Audited V2 panel')
    require(audit['producer_reference']==dict(path=str(ROOT/'scripts/ndx_new_cutoff_conditional_panel_v2_20260924.py'),sha256='a7a815c179e39de7678f1cb90da7488ee0157e8de636d768ac96f01b03f1f9b1'),'Audited producer')
    require(type(audit['increment_reconstruction_count']) is int and audit['increment_reconstruction_count']==1 and audit['independently_recomputed_tickers']==['PCAR'],'No repeated panel numerical audit')
    require(all(audit[k] is True for k in ('original_nineteen_five_frames_exact','unchanged_other99_gaps_exact','full_original101_and_incremental_sidecars_compared','typed_roundtrip_exact')),'Parent audit complete')
    for doc in (paneldoc,audit):
        require(all(doc[k] is False for k in ('fit_performed','point_in_time_verified','legal_training_input_admitted','promotion_allowed','execution_authorized')),'Panel permissions')
    panel=codec.decode_frames(paneldoc['panel'])
    require(panel['schema']=='LATEST_CONDITIONAL_TYPED_PANEL_V2' and all(panel[k] is False for k in codec.PANEL_FALSE),'Conditional V2 schema')
    require(panel['cutoff']=='2026-09-21' and panel['conditional_security_count']==outer['conditional_security_count']==audit['conditional_security_count']==20 and panel['conditional_issuer_count']==outer['conditional_issuer_count']==audit['conditional_issuer_count']==19,'20SID19issuer')
    require(panel['panel_content_sha256']==outer['panel_content_sha256']==audit['panel_content_sha256'] and {k:list(panel[k].shape) for k in codec.FRAMES}==audit['frame_shapes'],'Exact typed checksum/shapes')
    require(panel['observed_security_count']==101 and panel['observed_issuer_count']==100 and len(panel['observed_provenance_and_missing'])==len(paneldoc['original_evidence_and_projection'])==101 and len(paneldoc['incremental_evidence_and_projection'])==2,'Full101 sidecars')
    plan=outer['plan'];ctx=plan['context'];numerical=plan['fitter_source_hashes']
    require(ctx['panel_reference']==ref('panel') and ctx['panel_audit_reference']==ref('audit') and ctx['decision_cutoff']==panel['cutoff'] and ctx['previous_target_weights'] is None,'First new decision context')
    require(old['schema']=='LATEST_CONDITIONAL_ALL_K_REFIT_PLAN_V1' and old['cutoff']=='2026-09-17' and len(numerical)==25,'Original source metadata')
    require(numerical.get(str(ROOT/'backtest/ndx_dynamic_cutoff_refit_v2_research.py'))=='4bb005b7f88a1e806fc25dede38b0f15c42187c2aa6024d3eb32155d64abab75' and all(old['historical_expected_source_hashes'].get(p)==h for p,h in numerical.items()),'Full original fitter map')
    require(old['canonical_tasks'] and all(reader.exact(t['parameters'],ctx['parameters']) for t in old['canonical_tasks']),'Eight saved parameters')
    require(plan['cardinalities'][3]['k']==4 and not plan['cardinalities'][3]['necessary_bound_certificates'] and all(c['necessary_bound_certificates'] for c in plan['cardinalities'][:3]),'First nonexcluded k4')
    shards=[s for s in plan['shards'] if s['k']==4 and s['start']==0];require(len(shards)==1,'Unique first interval')
    projection=dict(panel_reference=ref('panel'),panel_content_sha256=panel['panel_content_sha256'],dates=[d.date().isoformat() for d in panel['returns'].index],columns=panel['returns'].columns.tolist(),returns=panel['returns'].values.tolist(),universe=[{k:r[k] for k in ('security_id','ticker','issuer_id','risk_chain')} for r in panel['universe'].to_dict('records')])
    return dict(plan=plan,plan_reference=ref('plan'),shard_id=shards[0]['shard_id'],panel=projection,start=0,stop=1,max_materialized_combinations=1,expected_fitter_source_hashes=numerical)


def producer_sources(documents):
    # Sealed new plan already binds planning/bounds dependencies, codec, pandas and 25 fitter sources.
    sources=dict(documents['plan']['source_hashes'])
    merge(sources,reader.MATERIALIZER_SOURCES)
    merge(sources,{str(PRODUCER):PRODUCER_SHA})
    merge(sources,{ref(k)['path']:ref(k)['sha256'] for k in BOUND})
    merge(sources,codec.LOADED)
    require(all(sources.get(p)==h for p,h in documents['plan']['plan']['fitter_source_hashes'].items()),'Numerical closure missing')
    require(all(sources.get(p)==h for p,h in documents['plan']['plan']['loaded_mathematical_source_hashes'].items()),'Mathematical closure missing')
    return sources


def verify_document(value,documents):
    args=project(documents);expected_sources=producer_sources(documents)
    expected=dict(schema='SOURCE_BOUND_NEW_CUTOFF_BOUNDED_MATERIALIZATION_V1',scope='CONDITIONAL_RESEARCH_TASK_INPUTS_NOT_EXECUTION',materialization=value['materialization'],input_references={k:ref(k) for k in BOUND},source_hashes=expected_sources,
      selected_slice_reason='FIRST_LEXICOGRAPHIC_COMBINATION_OF_FIRST_NONEXCLUDED_K_FOR_INTERFACE_VALIDATION_NOT_SCORE_SELECTION',external_direct_source_bytes_verified=True,materializer_invocation_count=1,combination_enumeration_performed=True,enumerated_combination_count=1,actual_fitter_invocation_count=0,**dict.fromkeys(FALSE,False))
    require(reader.exact(value,expected),'Full outer materialization/source contract')
    return reader.verify_materialized(value=value['materialization'],**args),expected_sources


def build():
    require(PRODUCER_SHA is not None and CANDIDATE_SHA is not None and BOUND['plan'][1] is not None,'Actual hard anchors pending')
    sources=dict(LOADED);guard(sources);documents={}
    for role in BOUND:
        r=ref(role);raw=Path(r['path']).read_bytes();require(codec.sha(raw)==r['sha256'],'Consumed hard parent bytes')
        documents[role]=codec.loads(raw);sources[r['path']]=r['sha256']
    raw=CANDIDATE.read_bytes();require(codec.sha(raw)==CANDIDATE_SHA,'Hard candidate bytes');sources[str(CANDIDATE)]=CANDIDATE_SHA
    expected=producer_sources(documents);merge(sources,expected);guard(sources)
    result,verified=verify_document(codec.loads(raw),documents);require(verified==expected,'Source closure changed')
    report=dict(schema='NEW_CUTOFF_MATERIALIZATION_INDEPENDENT_READBACK_V1',status='PASSED',candidate_reference=dict(path=str(CANDIDATE),sha256=CANDIDATE_SHA),producer_reference=dict(path=str(PRODUCER),sha256=PRODUCER_SHA),input_references={k:ref(k) for k in BOUND},source_hashes=sources,pure_readback=result,independent_materialization_readback_count=1,actual_fitter_invocation_count=0,materializer_called=False,production_prepare_called=False,panel_numerical_audit_repeated=False,**dict.fromkeys(FALSE,False))
    guard(sources);return report


def publish():
    require(not OUTPUT.exists(),'Audit already exists')
    require(OUTPUT.parent.is_dir() and {p.name for p in OUTPUT.parent.iterdir()}=={'materialized.json'},'Exact candidate-only namespace')
    value=build();guard(value['source_hashes']);raw=codec.pretty(value)
    with OUTPUT.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
    guard(value['source_hashes']);require(OUTPUT.read_bytes()==raw and {p.name for p in OUTPUT.parent.iterdir()}=={'materialized.json',OUTPUT.name},'Audit readback differs')
    return dict(path=str(OUTPUT),sha256=codec.sha(raw))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--publish',action='store_true');a=p.parse_args()
    require(a.publish,'Explicit --publish required');print(json.dumps(publish()))
