"""Historical cross-k task plan only. Never fits, imports results, or publishes."""
from copy import deepcopy
import argparse
import hashlib
import json
from pathlib import Path
import sys
import pandas as pd
import yaml
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backtest import ndx_conditional_panel_incremental_plan_research as enumeration
from scripts import ndx_historical_single_target_independent_audit_20260919 as target_reader
from scripts import ndx_twenty_historical_inputs_independent_audit_20260919 as input_reader
archive=target_reader.archive
BASE=ROOT/'data/cache/research'
INPUT=target_reader.INPUT
INPUT_AUDIT=target_reader.AUDIT
TARGET=dict(path=str(target_reader.TARGET_PATH),sha256='4d174d9263153f7df77b7c4357ed18eb13a2a8eb9194781a642d923762af90b6')
TARGET_AUDIT=dict(path=str(Path(TARGET['path']).parent/'independent_readback.json'),sha256='a3d18620288e95be31555a0226c935b8c5926c4aa47fd0e45efc5848b593890b')
SEARCH=dict(path=str(BASE/'latest_conditional_input_readiness_20260919_v1/observed_inputs/search.yaml'),sha256='41c26814561224ea6e96113092595f116bdec5845359188dbbd94b9f9b7b0b4c')
PURE_SHA='9876a6d28e575e5a96d2db6678da77c910c0642ab2b0d65ba5154405342b53f6'
LOADED={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__).resolve(),*(Path(m.__file__).resolve() for m in (enumeration,enumeration.core,enumeration.bounds,target_reader,input_reader)))}
archive.merge(LOADED,enumeration.bounds._LOADED)
archive.merge(LOADED,target_reader.LOADED)
archive.merge(LOADED,input_reader.LOADED)
FALSE=('fit_performed','result_imported','execution_performed','winner_selected','all_ndx_legal_pool_verified','historical_liquidity_qualification_verified','historical_risk_qualification_verified','point_in_time_verified','oos_evaluation_performed','promotion_allowed')


def exact(a,b):return target_reader.exact(a,b)
def digest(value):return enumeration.core.canonical_sha(value)


def historical_view(document):
    if document['schema']!='SOURCE_BOUND_TWENTY_CONDITIONAL_HISTORICAL_INPUTS_V1' or any(document[k] is not False for k in ('fit_performed','execution_performed','point_in_time_verified','legal_training_input_admitted','promotion_allowed','latest_weights_backfilled')):raise ValueError('Conditional historical input scope required')
    prices=document['prices'];calendar=prices['calendar'];frame=target_reader.typed.decode(prices['returns']);close=target_reader.typed.decode(prices['nominal_close'])
    if len(calendar)!=253 or len(frame)!=252 or len(close)!=253 or [d.date().isoformat() for d in frame.index]!=calendar[1:] or [d.date().isoformat() for d in close.index]!=calendar or calendar[126]!='2026-03-18' or calendar[127]!='2026-03-19' or calendar[-1]!='2026-09-17' or prices['fit_return_dates']!=calendar[1:127] or prices['evaluation_return_dates']!=calendar[127:]:raise ValueError('Historical first126 and forward126 must remain separated')
    rows=deepcopy(document['candidate_coordinate_and_risk_rows']);tickers=sorted(r['ticker'] for r in rows)
    if len(rows)!=14 or len(set(tickers))!=14 or len({r['security_id'] for r in rows})!=14 or len({r['issuer_id'] for r in rows})!=14:raise ValueError('Exact fourteen conditional coordinates required')
    provenance=document['candidate_full_original_provenance']
    if len(provenance)!=101 or len({r['ticker'] for r in provenance})!=101:raise ValueError('Preserve all 101 observation/gap rows')
    # Private numerical view for the frozen dynamic-cutoff enumeration utility.
    # This is not an assembled/authenticated latest or historical liquidity panel.
    panel=dict(schema='LATEST_CONDITIONAL_TYPED_PANEL_V1',scope=enumeration.core.SCOPE,cutoff='2026-03-18',
        universe=pd.DataFrame(rows),returns=frame.loc[:,tickers].iloc[:126].copy(deep=True),nominal_close=close.loc[:,tickers].iloc[:127].copy(deep=True),
        **dict.fromkeys(enumeration.core.FALSE,False))
    panel['panel_content_sha256']=enumeration.core.panel_digest(panel)
    return panel


def attach_completed_reference(tasks,target,numerical_sources,panel):
    """Called only after hard target and independent audit bytes fully verify."""
    task=target['task'];base={k:v for k,v in task.items() if k!='task_id'}
    if task.get('task_id')!=target_reader.JOB or digest(base)!=task['task_id'] or target['job_id']!=task['task_id'] or task['cutoff']!='2026-03-18':raise ValueError('Only the exact independently audited historical job may be referenced')
    if not exact(target['result']['source_hashes'],numerical_sources):raise ValueError('Frozen fitter sources differ from completed historical result')
    matches=[row for row in tasks if row['task_id']==task['task_id']]
    if len(matches)!=1 or not exact(matches[0]['task'],base):raise ValueError('Completed structure/parameters do not match historical task plan')
    row=matches[0];ids=sorted(base['selected']);tickers=[base['selected'][s]['ticker'] for s in ids]
    matrix=digest(dict(dates=[d.date().isoformat() for d in panel['returns'].index],tickers=tickers,returns=panel['returns'][tickers].to_numpy().tolist()))
    if row['fit_data_sha256']!=matrix or row['input_equivalence_sha256']!=digest(dict(task=base,fit_data_sha256=matrix,fitter_source_hashes=numerical_sources)):raise ValueError('Completed selected matrix/input equivalence differs')
    # Independent scalar reader uses the original fitter payload convention.
    target_reader.scalar.inspect_result(target['result'],task,dict(returns=target_reader.typed.prior.frame_payload(panel['returns'])))
    for item in tasks:
        item.update(status='PENDING_HISTORICAL_FIT',completed_external_reference=None,result_reused=False)
    row.update(status='COMPLETED_HISTORICAL_RESULT_EXTERNAL_REFERENCE_NOT_IMPORTED',completed_external_reference=deepcopy(TARGET))


def build():
    if LOADED[str(Path(enumeration.__file__).resolve())]!=PURE_SHA:raise ValueError('Frozen enumeration source differs')
    sources=dict(LOADED);read=target_reader.read
    document=read(INPUT,sources);input_audit=read(INPUT_AUDIT,sources);target=read(TARGET,sources);audit=read(TARGET_AUDIT,sources)
    input_reader.verify(input_audit);target_reader.verify(audit)
    if not exact(input_audit['artifact_reference'],INPUT) or not exact(audit['target_reference'],TARGET) or not exact(audit['input_reference'],INPUT):raise ValueError('Hard independent readback lineage differs')
    for value in (document,input_audit,target,audit):archive.merge(sources,value['historical_expected_source_hashes'])
    raw=Path(SEARCH['path']).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=SEARCH['sha256']:raise ValueError('Frozen original search contract differs')
    archive.merge(sources,{SEARCH['path']:SEARCH['sha256']});search=yaml.safe_load(raw)['search_contract']
    parameters={k:search[k] for k in enumeration.PARAMETERS}
    if not exact(parameters,target_reader.scalar.PARAMS) or search['window_days']!=126 or search['step_days']!=21:raise ValueError('Original fit/evaluation/step/parameters differ')
    numerical=target_reader.scalar.numerical_sources._sources();archive.merge(sources,numerical)
    partition=archive.verify_expected_sources(sources,archive.load_contract())
    panel=historical_view(document)
    cards,tasks=enumeration.enumerate_inputs(panel,parameters,numerical,exact_limit=search['exact_enumeration_max_feasible_combinations'])
    attach_completed_reference(tasks,target,numerical,panel)
    if not exact(partition,archive.verify_expected_sources(sources,archive.load_contract())):raise ValueError('Source partition changed during plan preparation')
    return dict(schema='HISTORICAL_FOURTEEN_CROSS_K_TASK_PLAN_V1',cutoff=panel['cutoff'],fit_calendar=document['prices']['calendar'][1:127],execution_calendar=document['prices']['calendar'][126:],
        input_reference=deepcopy(INPUT),independent_input_audit_reference=deepcopy(INPUT_AUDIT),completed_historical_target_reference=deepcopy(TARGET),independent_target_audit_reference=deepcopy(TARGET_AUDIT),
        cardinalities=cards,tasks=tasks,parameters=parameters,exact_enumeration_limit=search['exact_enumeration_max_feasible_combinations'],
        nonempty_combinations=sum(c['combinations'] for c in cards),necessary_bound_excluded_combinations=sum(c['combinations'] for c in cards if c['necessary_bound_certificates']),
        canonical_task_count=len(tasks),completed_external_reference_count=1,pending_historical_fit_count=len(tasks)-1,
        historical_numerical_view=target_reader.typed.prior.frame_payload(panel['returns']),candidate_coordinate_and_risk_rows=deepcopy(document['candidate_coordinate_and_risk_rows']),
        complete_101_provenance_and_gaps=deepcopy(document['candidate_full_original_provenance']),supplemental_dated_provenance=deepcopy(document['candidate_supplemental_dated_provenance']),
        research_role_assumptions={k:document[k] for k in ('coordinate_interval_role','latest_liquidity_role','risk_label_role')},
        scope='FOURTEEN_RETROSPECTIVE_CONDITIONAL_SUBSET_NOT_ALL_NDX_ADMISSION',latest_cutoff_results_imported=False,anchored_variants_evaluated=False,
        numerical_source_hashes=numerical,historical_expected_source_hashes=sources,archive_resolution=partition,**dict.fromkeys(FALSE,False))


def verify(value):
    if not exact(value,build()):raise ValueError('Complete historical plan/source/task/scope reconstruction differs')


def publish_verified(path,value):
    verify(value)
    saved=target_reader.exclusive_publish(path,value)
    if not exact(archive.verify_expected_sources(value['historical_expected_source_hashes'],archive.load_contract()),value['archive_resolution']):raise ValueError('Source drift after plan publication')
    return saved


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);args=parser.parse_args()
    print(json.dumps(publish_verified(args.output,build())))
