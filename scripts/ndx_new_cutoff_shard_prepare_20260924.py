"""Source-bound interval plan only; no combination enumeration or fitting."""
import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys

import yaml

SOURCE=Path(__file__).resolve();ROOT=SOURCE.parents[1];BASE=ROOT/'data/cache/research'
sys.path.insert(0,str(ROOT))
from backtest import ndx_issuer_shard_prepare_research as planning
from backtest import ndx_dynamic_cutoff_refit_v2_research as fitter
from scripts import ndx_new_cutoff_typed_panel_independent_readback_20260923 as reader

OUTPUT=BASE/'new_cutoff_shard_prepare_20260924_v1/plan.json'
PLANNING_SHA='722f48952a6d0c8c878df76eedeb0b8ca3b1e3feeb77560598414890ae00a4ec'
READER_SHA='0b5fbb5ae38a91e7919c16b9846bf165b72c7b2aae89f281125ee23ad18fe3f9'
FITTER_SHA='4bb005b7f88a1e806fc25dede38b0f15c42187c2aa6024d3eb32155d64abab75'
BOUND={
 'panel':('new_cutoff_conditional_panel_20260923_v1/panel.json','15c5d9449f10abeb7379baad9fd2b117b8fb84a24582190cf01b8d5b8dd8b047'),
 'audit':('new_cutoff_conditional_panel_20260923_v1/independent_typed_readback.json','f3e55a68487c78f42d5b4dd7da12461177d472edcab89499697bbaa405c66fa8'),
 'old_plan_metadata':('latest_conditional_all_k_refit_20260919_v1/plan.json','7b9cd1fd9dbbc9c42625495e73803e633a81f86039e1e1113ba9de3d295c52f0'),
 'search':('latest_conditional_input_readiness_20260919_v1/observed_inputs/search.yaml','41c26814561224ea6e96113092595f116bdec5845359188dbbd94b9f9b7b0b4c'),
}
PARAMETERS=dict(fit_days=126,shrinkage_intensity=.35,turnover_anchor_strength=.25,max_single_weight=.45,
 min_single_weight=.05,top_weight_cap=.8,minimum_effective_n_ratio=.7,risk_chain_top1_cap=.55)
LOADED={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in
 (SOURCE,Path(planning.__file__).resolve(),Path(reader.__file__).resolve(),Path(fitter.__file__).resolve(),Path(yaml.__file__).resolve())}
FALSE=('combination_enumeration_performed','task_inputs_materialized','fit_performed','old_fit_results_reused',
 'old_plan_build_called','panel_audit_repeated','execution_authorized','point_in_time_verified','promotion_allowed',
 'legal_training_input_admitted','full_transitive_source_closure_reverified','complete_ndx_eligible_pool_verified',
 'continuous_weight_space_exhausted','winner_selected','dual_benchmark_evaluation_performed','oos_evaluation_performed')


def require(ok,message):
    if not ok:raise ValueError(message)


def encode(value):return (json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
def reference(role):
    path,digest=BOUND[role];return dict(path=str(BASE/path),sha256=digest)


def guard(sources):
    require(len(PLANNING_SHA)==64,'Reviewed planner SHA pending')
    for module,digest in ((planning,PLANNING_SHA),(reader,READER_SHA),(fitter,FITTER_SHA)):
        require(LOADED[str(Path(module.__file__).resolve())]==digest,'Loaded implementation differs')
    for path,digest in {**sources,**LOADED}.items():
        require(hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest,'Source drift: '+path)


def inputs_from_documents(documents,numerical_sources):
    """Read sealed metadata/typed cells; never call reader.build or a fitter."""
    candidate,audit,previous,search=(documents[k] for k in ('panel','audit','old_plan_metadata','search'))
    require(candidate['schema']=='NEW_CUTOFF_CONDITIONAL_TYPED_PANEL_DOCUMENT_V1' and
        audit['schema']=='NEW_CUTOFF_TYPED_PANEL_INDEPENDENT_READBACK_V1' and audit['status']=='PASSED',
        'Reviewed candidate and audit schemas required')
    require(audit['candidate_reference']==reference('panel') and audit['producer_reference']==dict(
        path=str(ROOT/'scripts/ndx_new_cutoff_conditional_panel_20260923.py'),
        sha256='95bc442c379acb32b4c5d1c58a2eca6e0e2ad97bca9538249affe1a5e937236c'), 'Audit parent differs')
    require(audit['full_101_gap_and_sidecar_compared'] is True and audit['typed_roundtrip_exact'] is True and
        type(audit['reconstruction_count']) is int and audit['reconstruction_count']==1,'Complete independent audit required')
    for document in (candidate,audit):
        require(all(document[k] is False for k in ('legal_training_input_admitted','point_in_time_verified','promotion_allowed',
            'execution_authorized','full_transitive_source_closure_reverified')),'Source authority upgraded')
    require(all(audit[k] is False for k in ('producer_called','panel_core_called','old_raw_oracle_called','fit_performed')),
        'Saved audit operation scope differs')
    decoded=reader.decode_frames(candidate['panel'])
    require(all(decoded[k] is False for k in reader.PANEL_FALSE),'Panel scope upgraded')
    require(decoded['cutoff']=='2026-09-21' and audit['panel_content_sha256']==decoded['panel_content_sha256'],
        'Actual panel cutoff/checksum differs')
    require(decoded['observed_security_count']==audit['observed_security_count']==101 and
        decoded['observed_issuer_count']==100 and len(decoded['observed_provenance_and_missing'])==101 and
        len(candidate['original_evidence_and_projection'])==101,'Complete observation denominator required')
    require({key:list(decoded[key].shape) for key in reader.FRAMES}==audit['frame_shapes'], 'Audited frame shapes differ')
    rows=decoded['universe'].to_dict('records');groups={}
    require(len(rows)==decoded['conditional_security_count']==audit['conditional_security_count']==19 and
        len({row['security_id'] for row in rows})==19,'This version binds all 19 actual panel rows')
    for row in rows:groups.setdefault(row['issuer_id'],[]).append(row['security_id'])
    require(len(groups)==decoded['conditional_issuer_count']==audit['conditional_issuer_count']==18,
        'Actual distinct issuer count differs')
    require(previous['schema']=='LATEST_CONDITIONAL_ALL_K_REFIT_PLAN_V1' and previous['cutoff']=='2026-09-17',
        'Old metadata reference differs; no old tasks may be reused')
    params={key:search['search_contract'][key] for key in PARAMETERS}
    require(reader.canonical(params)==reader.canonical(PARAMETERS),'Original eight parameters changed')
    require(all(reader.canonical(task['parameters'])==reader.canonical(params) for task in previous['canonical_tasks'])
        and bool(previous['canonical_tasks']), 'Saved parameter metadata inconsistent')
    require(len(numerical_sources)==25 and numerical_sources.get(str(Path(fitter.__file__).resolve()))==FITTER_SHA and
        all(previous['historical_expected_source_hashes'].get(path)==digest for path,digest in numerical_sources.items()),
        'Complete original numerical closure differs')
    return sorted(groups.items()),params,decoded


def build():
    sources=dict(LOADED);guard(sources);documents={}
    for role in BOUND:
        ref=reference(role);raw=Path(ref['path']).read_bytes()
        require(hashlib.sha256(raw).hexdigest()==ref['sha256'],'Consumed source bytes differ')
        sources[ref['path']]=ref['sha256']
        documents[role]=yaml.safe_load(raw) if role=='search' else reader.loads(raw)
    numerical=fitter._sources()
    groups,parameters,decoded=inputs_from_documents(documents,numerical)
    for mapping in (planning.LOADED,planning.bounds._LOADED,reader.LOADED,numerical):
        for path,digest in mapping.items():
            require(path not in sources or sources[path]==digest,'Conflicting source reference')
            sources[path]=digest
    guard(sources)
    result=planning.prepare_issuer_shards(groups=groups,panel_reference=reference('panel'),
        panel_audit_reference=reference('audit'),decision_cutoff=decoded['cutoff'],parameters=parameters,
        fitter_source_hashes=numerical,previous_target_weights=None,shard_size=1000,max_shards=1000)
    guard(sources)
    return dict(schema='SOURCE_BOUND_NEW_CUTOFF_SHARD_PREPARE_V1',scope='CONDITIONAL_RESEARCH_PLAN_NOT_EXECUTION',
        plan=result,input_references={role:reference(role) for role in BOUND},source_hashes=sources,
        panel_content_sha256=decoded['panel_content_sha256'],candidate_cutoff=decoded['cutoff'],
        observed_security_count=101,observed_issuer_count=100,conditional_security_count=19,conditional_issuer_count=18,
        complete_observed_provenance_and_missing=deepcopy(decoded['observed_provenance_and_missing']),
        preserved_evidence_sidecar_reference=dict(reference('panel'),json_pointer='/original_evidence_and_projection'),
        policy='FIRST_DECISION_NO_PRIOR_TARGET_ALL_THREE_WEIGHT_SPECS_WITHOUT_ALIAS_DEDUPLICATION',
        external_direct_source_bytes_verified=True,planner_invocation_count=1,**dict.fromkeys(FALSE,False))


def publish():
    require(not OUTPUT.parent.exists(),'Fresh fixed namespace required; never rebuild a completed plan')
    value=build();guard(value['source_hashes']);raw=encode(value)
    OUTPUT.parent.mkdir(parents=True,exist_ok=False)
    with OUTPUT.open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
    guard(value['source_hashes']);require(OUTPUT.read_bytes()==raw,'Published bytes differ')
    require({path.name for path in OUTPUT.parent.iterdir()}=={'plan.json'},'Unexpected output namespace')
    return dict(path=str(OUTPUT),sha256=hashlib.sha256(raw).hexdigest())


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--publish',action='store_true');args=parser.parse_args()
    require(args.publish,'Explicit --publish required');print(json.dumps(publish()))
