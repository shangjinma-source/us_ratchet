"""Independent historical task denominator and numerical-input audit; no fit."""
import argparse
import copy
from fractions import Fraction
import hashlib
import itertools
import json
import math
from pathlib import Path
import sys
import yaml
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import ndx_historical_single_target_independent_audit_20260919 as target_reader
from scripts import ndx_twenty_historical_inputs_independent_audit_20260919 as input_reader
archive=target_reader.archive
publish=target_reader.exclusive_publish
BASE=ROOT/'data/cache/research'
PLAN_PATH=BASE/'historical_fourteen_cross_k_20260923_v1/plan.json'
PLAN_SHA='bd2f64aa33013330d4371c4266556cb4f7b04a27c994b4ad6553025516379f9f'
OWNER=ROOT/'scripts/ndx_historical_fourteen_cross_k_plan_20260923.py'
OWNER_SHA='6f1b3ebece10526e0fc606673d448a720e86bea861ffafb3487dec0156d71896'
INPUT=target_reader.INPUT;INPUT_AUDIT=target_reader.AUDIT
TARGET=dict(path=str(target_reader.TARGET_PATH),sha256='4d174d9263153f7df77b7c4357ed18eb13a2a8eb9194781a642d923762af90b6')
TARGET_AUDIT=dict(path=str(Path(TARGET['path']).parent/'independent_readback.json'),sha256='a3d18620288e95be31555a0226c935b8c5926c4aa47fd0e45efc5848b593890b')
SEARCH=dict(path=str(BASE/'latest_conditional_input_readiness_20260919_v1/observed_inputs/search.yaml'),sha256='41c26814561224ea6e96113092595f116bdec5845359188dbbd94b9f9b7b0b4c')
PLAN_FALSE=('fit_performed','result_imported','execution_performed','winner_selected','all_ndx_legal_pool_verified','historical_liquidity_qualification_verified','historical_risk_qualification_verified','point_in_time_verified','oos_evaluation_performed','promotion_allowed')
LOADED={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__).resolve(),Path(target_reader.__file__).resolve(),Path(input_reader.__file__).resolve(),archive.SOURCE,archive.drift.SOURCE,Path(publish.__code__.co_filename).resolve())}


def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def exact(left,right):return digest(left)==digest(right)
def read(ref,sources):return target_reader.read(ref,sources)


def independent_certificates(k,parameters):
    # Universal capacity, minimum-mass and pigeonhole top-three bounds.
    # Fractions deliberately reproduce the frozen widened acceptance envelope.
    margin=Fraction(k+1,10**12);tolerance=Fraction(1,10**9)
    lower=1-tolerance-margin;upper=1+tolerance+margin
    cap=Fraction(str(parameters['max_single_weight']))
    floor=Fraction(str(parameters['min_single_weight']))
    top=Fraction(str(parameters['top_weight_cap']))
    comparisons=[('MAX_SINGLE_CAPACITY_BELOW_MINIMUM_SIMPLEX_MASS',k*(cap+tolerance)+margin,'<',lower),
        ('MIN_SINGLE_REQUIRED_MASS_ABOVE_MAXIMUM_SIMPLEX_MASS',k*max(Fraction(0),floor-tolerance)-margin,'>',upper),
        ('TRUE_TOP3_UNIVERSAL_LOWER_BOUND_ABOVE_ACCEPTED_CAP',Fraction(min(k,3),k)*lower,'>',top+tolerance+margin)]
    def rational(x):return dict(numerator=str(x.numerator),denominator=str(x.denominator))
    return [dict(reason=reason,left=rational(a),comparison=op,right=rational(b),strict_gap=rational(abs(a-b)),
        arithmetic='EXACT_RATIONAL_DECIMAL_INPUT_WITH_CONSERVATIVE_TOLERANCE_AND_ROUNDING_PADDING')
        for reason,a,op,b in comparisons if (a<b if op=='<' else a>b)]


def first_window(document):
    calendar=document['prices']['calendar'];encoded=document['prices']['returns'];rows=document['candidate_coordinate_and_risk_rows']
    if len(calendar)!=253 or calendar[126]!='2026-03-18' or calendar[127]!='2026-03-19' or calendar[-1]!='2026-09-17':raise ValueError('Historical first126/forward126 boundary differs')
    if document['prices']['fit_return_dates']!=calendar[1:127] or document['prices']['evaluation_return_dates']!=calendar[127:]:raise ValueError('Declared fit/evaluation split differs')
    full=input_reader.matrix(encoded,calendar[1:],encoded['columns'])
    if len(rows)!=14 or any(len({r[k] for r in rows})!=14 for k in ('security_id','issuer_id','ticker')):raise ValueError('Fourteen unique conditional security/issuer/channel coordinates required')
    tickers=sorted(r['ticker'] for r in rows);positions=[encoded['columns'].index(t) for t in tickers]
    values=[[r[i] for i in positions] for r in full[:126]]
    if any(v<=-1 for row in values for v in row):raise ValueError('Positive price-derived gross returns required')
    if len(document['candidate_full_original_provenance'])!=101 or len({r['ticker'] for r in document['candidate_full_original_provenance']})!=101:raise ValueError('Complete 101 provenance/gap denominator required')
    return dict(type='dataframe',index_kind='DatetimeIndex',index=[d+'T00:00:00' for d in calendar[1:127]],columns=tickers,dtypes=['float64']*14,data=values)


def expected_task(selected,spec,parameters,frame,numerical):
    ids=sorted(selected);selected={s:{k:selected[s][k] for k in ('ticker','issuer_id','risk_chain')} for s in ids}
    task=dict(selected=selected,holding_count=len(ids),weight_spec=spec,cutoff='2026-03-18',parameters=parameters,previous_target_weights=None)
    tickers=[selected[s]['ticker'] for s in ids];positions=[frame['columns'].index(t) for t in tickers]
    matrix=digest(dict(dates=[d[:10] for d in frame['index']],tickers=tickers,returns=[[r[i] for i in positions] for r in frame['data']]))
    identifier=digest(task)
    return dict(task_id=identifier,input_equivalence_sha256=digest(dict(task=task,fit_data_sha256=matrix,fitter_source_hashes=numerical)),fit_data_sha256=matrix,task=task,
        status='COMPLETED_HISTORICAL_RESULT_EXTERNAL_REFERENCE_NOT_IMPORTED' if identifier==target_reader.JOB else 'PENDING_HISTORICAL_FIT',
        completed_external_reference=TARGET if identifier==target_reader.JOB else None,result_reused=False)


def independent_rows(document,parameters,frame,numerical):
    # This pool has exactly one security per issuer. Do not assume ticker sorting.
    rows=sorted(document['candidate_coordinate_and_risk_rows'],key=lambda r:r['issuer_id'])
    for k in range(1,15):
        if independent_certificates(k,parameters):continue
        for selected in itertools.combinations(rows,k):
            mapping={r['security_id']:r for r in selected}
            for spec in ('equal_weight','constrained_fixed_shrinkage'):
                yield expected_task(mapping,spec,parameters,frame,numerical)


def inspect(value,document,target,parameters,numerical,sources,partition,limit):
    if not exact(parameters,target_reader.scalar.PARAMS) or type(limit) is not int or limit!=50000:raise ValueError('Original hard parameters/exact budget required')
    frame=first_window(document)
    cards=[dict(k=k,combinations=math.comb(14,k),necessary_bound_certificates=independent_certificates(k,parameters)) for k in range(1,15)]
    expected_count=2*sum(c['combinations'] for c in cards if not c['necessary_bound_certificates'])
    if expected_count!=31828 or type(value['tasks']) is not list or len(value['tasks'])!=expected_count:raise ValueError('Complete 31828 canonical task denominator required')
    completed=None;seen=set()
    for actual,expected in zip(value['tasks'],independent_rows(document,parameters,frame,numerical),strict=True):
        if not exact(actual,expected) or actual['task_id'] in seen:raise ValueError('Ordered task identity/matrix/spec/reference/source differs')
        seen.add(actual['task_id'])
        if expected['completed_external_reference'] is not None:completed=expected
    if completed is None or not exact(target['task'],dict(completed['task'],task_id=target_reader.JOB)) or target['job_id']!=target_reader.JOB or not exact(target['result']['source_hashes'],numerical):raise ValueError('Unique original historical result input/source is not equivalent')
    diagnostics=target_reader.scalar.inspect_result(target['result'],target['task'],dict(returns=frame))
    expected=dict(schema='HISTORICAL_FOURTEEN_CROSS_K_TASK_PLAN_V1',cutoff='2026-03-18',fit_calendar=document['prices']['calendar'][1:127],execution_calendar=document['prices']['calendar'][126:],
        input_reference=INPUT,independent_input_audit_reference=INPUT_AUDIT,completed_historical_target_reference=TARGET,independent_target_audit_reference=TARGET_AUDIT,
        cardinalities=cards,tasks=value['tasks'],parameters=parameters,exact_enumeration_limit=limit,nonempty_combinations=16383,
        necessary_bound_excluded_combinations=sum(c['combinations'] for c in cards if c['necessary_bound_certificates']),canonical_task_count=expected_count,completed_external_reference_count=1,pending_historical_fit_count=expected_count-1,
        historical_numerical_view=frame,candidate_coordinate_and_risk_rows=document['candidate_coordinate_and_risk_rows'],complete_101_provenance_and_gaps=document['candidate_full_original_provenance'],
        supplemental_dated_provenance=document['candidate_supplemental_dated_provenance'],research_role_assumptions={k:document[k] for k in ('coordinate_interval_role','latest_liquidity_role','risk_label_role')},
        scope='FOURTEEN_RETROSPECTIVE_CONDITIONAL_SUBSET_NOT_ALL_NDX_ADMISSION',latest_cutoff_results_imported=False,anchored_variants_evaluated=False,
        numerical_source_hashes=numerical,historical_expected_source_hashes=sources,archive_resolution=partition,**dict.fromkeys(PLAN_FALSE,False))
    if not exact(value,expected):raise ValueError('Full historical plan/provenance/scope/source differs')
    return dict(security_count=14,issuer_count=14,observation_provenance_count=101,all_nonempty_combinations=16383,
        necessary_bound_excluded_combinations=469,canonical_task_count=31828,completed_external_reference_count=1,pending_historical_fit_count=31827,
        fit_rows=126,fit_end='2026-03-18',execution_observation_count=127,first_next_open='2026-03-19',
        all_ordered_task_inputs_independently_reconstructed=True,all_cardinalities_1_through_14_preserved=True,
        complete_provenance_and_gaps_exact=True,completed_external_reference_diagnostics=diagnostics)


def producer_sources(documents,numerical):
    names=('ndx_conditional_panel_incremental_plan_research','ndx_latest_conditional_panel_research','ndx_membership_cardinality_plan_research',
        'ndx_cardinality_search','ndx_membership_scope_research','ndx_dynamic_cutoff_refit_research')
    sources={str(OWNER):OWNER_SHA}
    for name in names:
        path=(ROOT/'backtest'/f'{name}.py').resolve();archive.merge(sources,{str(path):hashlib.sha256(path.read_bytes()).hexdigest()})
    archive.merge(sources,target_reader.LOADED);archive.merge(sources,input_reader.LOADED)
    for ref,value in documents:
        archive.merge(sources,{ref['path']:ref['sha256']});archive.merge(sources,value['historical_expected_source_hashes'])
    archive.merge(sources,{SEARCH['path']:SEARCH['sha256']});archive.merge(sources,numerical)
    return sources


def build():
    if PLAN_SHA is None or OWNER_SHA is None:raise ValueError('Await hard published historical plan and producer source')
    sources=dict(LOADED);plan_ref=dict(path=str(PLAN_PATH),sha256=PLAN_SHA);value=read(plan_ref,sources)
    refs=(INPUT,INPUT_AUDIT,TARGET,TARGET_AUDIT);docs=[read(ref,sources) for ref in refs]
    document,input_audit,target,target_audit=docs
    if input_audit['artifact_reference']!=INPUT or target_audit['target_reference']!=TARGET or target_audit['input_reference']!=INPUT:raise ValueError('Hard independent audits have inconsistent lineage')
    raw=Path(SEARCH['path']).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=SEARCH['sha256']:raise ValueError('Original contract changed')
    search=yaml.safe_load(raw)['search_contract']
    parameters={k:search[k] for k in target_reader.scalar.PARAMS}
    if search['window_days']!=126 or search['step_days']!=21:raise ValueError('Original evaluation and step differ')
    numerical=target_reader.scalar.numerical_sources._sources()
    expected_sources=producer_sources(list(zip(refs,docs)),numerical);archive.merge(sources,expected_sources)
    contract=archive.load_contract();partition=archive.verify_expected_sources(expected_sources,contract)
    details=inspect(value,document,target,parameters,numerical,expected_sources,partition,search['exact_enumeration_max_feasible_combinations'])
    return dict(schema='HISTORICAL_FOURTEEN_PLAN_INDEPENDENT_AUDIT_V1',plan_reference=plan_ref,input_reference=INPUT,independent_input_audit_reference=INPUT_AUDIT,
        completed_historical_target_reference=TARGET,independent_target_audit_reference=TARGET_AUDIT,details=details,
        producer_build_called=False,producer_enumeration_called=False,fitter_called=False,latest_results_imported=False,
        historical_expected_source_hashes=sources,archive_resolution=archive.verify_expected_sources(sources,contract),**dict.fromkeys(PLAN_FALSE,False))


def verify(value):
    if not exact(value,build()):raise ValueError('Complete independent historical plan readback differs')


def publish_verified(path,value):
    verify(value);saved=publish(path,value)
    if not exact(archive.verify_expected_sources(value['historical_expected_source_hashes'],archive.load_contract()),value['archive_resolution']):raise ValueError('Source drift after publication')
    return saved


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args();print(json.dumps(publish_verified(a.output,build())))
