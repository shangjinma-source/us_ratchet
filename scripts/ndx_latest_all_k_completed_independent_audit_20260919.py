"""Independent completed-prefix diagnostics; never run/check the owner's refit or solver."""
import argparse
import hashlib
import itertools
import json
import math
import sys
from collections import Counter
from datetime import date
from decimal import Decimal,localcontext
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backtest import ndx_root_price_archive_contract_research as archive
from backtest import ndx_dynamic_cutoff_refit_v2_research as numerical_sources
from scripts.ndx_latest_conditional_channels_20260919 import exclusive_publish
BASE=ROOT/'data/cache/research'
PLAN=BASE/'latest_conditional_all_k_refit_20260919_v1/plan.json'
PLAN_SHA='7b9cd1fd9dbbc9c42625495e73803e633a81f86039e1e1113ba9de3d295c52f0'
OWNER=ROOT/'scripts/ndx_latest_conditional_all_k_refit_20260919.py'
OWNER_SHA='4f6383a40c730d20a52fdb636570fffe23834a6bdb6cc06c738c4caa47a69898'
FALSE=('point_in_time_verified','promotion_allowed','execution_authorized','legal_training_input_admitted','dual_benchmark_evaluation_performed','whole_lot_execution_performed','oos_evaluation_performed','winner_selected','global_optimum_proven','strict_loader_validation_passed')
PARAMS=dict(fit_days=126,shrinkage_intensity=.35,turnover_anchor_strength=.25,max_single_weight=.45,min_single_weight=.05,top_weight_cap=.8,minimum_effective_n_ratio=.7,risk_chain_top1_cap=.55)
LOADED={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__).resolve(),archive.SOURCE,archive.drift.SOURCE,Path(numerical_sources.__file__).resolve(),Path(exclusive_publish.__code__.co_filename).resolve())}


def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def exact(a,b):return digest(a)==digest(b)
def read(ref,sources):
    path=Path(ref['path']).resolve();raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=ref['sha256']:raise ValueError('External file SHA differs')
    archive.merge(sources,{str(path):ref['sha256']});return json.loads(raw)
def number(value):
    if type(value) not in (int,float) or not math.isfinite(value):raise ValueError('Finite nonboolean original numeric value required')
    return Decimal(str(value))


def declared_partition(expected,contract):
    """Metadata comparison only; the complete union is byte-verified separately."""
    live=dict(contract['authority_source_hashes']);resolved=[];gaps=[]
    for path,sha in expected.items():
        if str(Path(path).resolve())!=path or not Path(path).is_absolute():raise ValueError('Absolute source required')
        row=contract['rows'].get(path)
        if row is None:archive.merge(live,{path:sha});continue
        if sha!=row['expected_historical_sha256']:raise ValueError('Historical SHA replaced')
        evidence=dict(original_path=path,expected_historical_sha256=sha,archived_path=row['archived_path'],archived_sha256=row['archived_sha256'],original_live_path_verified=False)
        if row['historical_expected_bytes_preserved']:resolved.append(dict(evidence,historical_bytes_exact=True))
        else:gaps.append(dict(evidence,historical_bytes_recovered=False,role='SEALED_CURRENT_OBSERVATION_NOT_HISTORICAL_BYTES'))
    return dict(live_verified_source_hashes=live,archive_resolutions=resolved,historical_gap_observations=gaps,historical_full_source_closure_recovered=False,point_in_time_verified=False,promotion_allowed=False)


def inspect_plan(plan,panel):
    if plan['canonical_task_count']!=764 or plan['alias_count']!=382 or plan['complete_issuer_unique_combinations']!=511:
        raise ValueError('Full 9-issuer denominator differs')
    universe=[dict(zip(panel['universe']['columns'],row)) for row in panel['universe']['data']]
    by_sid={r['security_id']:r for r in universe}
    if len(by_sid)!=9 or len({r['issuer_id'] for r in universe})!=9:raise ValueError('Hard conditional security/issuer denominator differs')
    tasks=plan['canonical_tasks'];expected=set()
    for k in range(4,10):
        for group in itertools.combinations(sorted(by_sid),k):
            for spec in ('equal_weight','constrained_fixed_shrinkage'):expected.add((group,spec))
    observed=set()
    for task in tasks:
        if task['task_id']!=digest({k:v for k,v in task.items() if k!='task_id'}) or not exact(task['parameters'],PARAMS) or task['previous_target_weights'] is not None:raise ValueError('Original task parameters/hash/prior differ')
        if task['cutoff']!='2026-09-17' or type(task['holding_count']) is not int or task['holding_count']!=len(task['selected']):raise ValueError('Task date/cardinality differs')
        for sid,row in task['selected'].items():
            if sid not in by_sid or not exact(row,{k:by_sid[sid][k] for k in ('ticker','issuer_id','risk_chain')}):raise ValueError('Task differs from hard panel identity')
        observed.add((tuple(sorted(task['selected'])),task['weight_spec']))
    if observed!=expected or len(tasks)!=len(expected) or [t['task_id'] for t in tasks]!=sorted(t['task_id'] for t in tasks):raise ValueError('Exact complete canonical combination/spec set differs')
    canonical={t['task_id']:t for t in tasks}
    if len(plan['anchor_aliases'])!=382 or len({a['canonical_task_id'] for a in plan['anchor_aliases']})!=382:raise ValueError('Complete unique alias denominator required')
    for alias in plan['anchor_aliases']:
        task=canonical[alias['canonical_task_id']]
        if task['weight_spec']!='constrained_fixed_shrinkage' or not exact(alias['selected'],task['selected']) or alias['numerical_equivalence_verified'] is not False or alias['actual_fitter_called'] is not False or alias['status']!='PENDING_REAL_PROBE_EQUIVALENCE_NOT_EVALUATED':raise ValueError('Anchor alias cannot claim a fitted/equivalent result')
    return canonical


def inspect_result(result,task,panel):
    if result['schema']!='ndx_dynamic_cutoff_refit_research_v2' or result['cutoff']!=task['cutoff'] or result['weight_spec']!=task['weight_spec'] or type(result['fit_row_count']) is not int or result['fit_row_count']!=126:raise ValueError('Original result schema/date/spec differs')
    for key in ('checkpoint_weights_used','point_in_time_verified','source_authenticity_verified','promotion_allowed','historical_task_evaluation_performed','order_generation_allowed'):
        if result[key] is not False:raise ValueError('Original numerical diagnostic scope differs')
    if not exact(result['declared_parameters'],{k:float(v) for k,v in PARAMS.items() if k!='fit_days'}):raise ValueError('Seven original numerical parameters differ')
    selected=task['selected'];sids=sorted(selected);tickers=[selected[s]['ticker'] for s in sids]
    if len(set(tickers))!=len(sids) or len({selected[s]['issuer_id'] for s in sids})!=len(sids):raise ValueError('Duplicate selected security/issuer')
    frame=panel['returns'];positions=[frame['columns'].index(t) for t in tickers]
    dates=[v[:10] for v in frame['index']]
    if len(dates)!=126 or dates!=sorted(set(dates)) or dates[-1]!=task['cutoff'] or any(date.fromisoformat(d).isoformat()!=d for d in dates):raise ValueError('Full actual 126-row matrix required')
    payload=dict(dates=dates,tickers=tickers,returns=[[r[p] for p in positions] for r in frame['data']])
    if result['fit_data_sha256']!=digest(payload) or result['fit_start']!=dates[0] or result['fit_end']!=dates[-1]:raise ValueError('Independent actual matrix digest/date differs')
    if result['previous_target_weights']!={} or type(result['previous_target_weights']) is not dict or number(result['surviving_anchor_mass'])!=0 or number(result['effective_anchor_strength'])!=0:raise ValueError('No-prior diagnostic changed')
    if set(result['anchor_by_security'])!=set(sids) or any(number(v)!=0 for v in result['anchor_by_security'].values()):raise ValueError('Nonzero/boolean anchor')
    if not exact(result['risk_chains_by_security'],{s:selected[s]['risk_chain'] for s in sids}) or set(result['targets'])!=set(sids):raise ValueError('Risk/target coordinates differ')
    weights={};chains={}
    for sid in sids:
        row=result['targets'][sid]
        if set(row)!={'ticker','issuer_id','target_weight'} or row['ticker']!=selected[sid]['ticker'] or row['issuer_id']!=selected[sid]['issuer_id']:raise ValueError('Exact result target identity differs')
        weight=number(row['target_weight'])
        if weight<0:raise ValueError('Negative weight')
        if task['weight_spec']=='equal_weight' and row['target_weight']!=1./len(sids):raise ValueError('Equal-weight result is not original exact equal weight')
        weights[sid]=weight;chain=selected[sid]['risk_chain'];chains[chain]=chains.get(chain,Decimal(0))+weight
    with localcontext() as ctx:
        ctx.prec=50;ordered=sorted(weights.values(),reverse=True);total=sum(ordered);tolerance=Decimal('1e-9')
        if abs(total-1)>tolerance:raise ValueError('Target simplex differs')
        effective=1/sum(v*v for v in ordered)
        checks=dict(MAX_SINGLE_WEIGHT=ordered[0]<=Decimal('.45')+tolerance,MIN_SINGLE_WEIGHT=ordered[-1]>=Decimal('.05')-tolerance,
            SECURITY_TOP3_WEIGHT=sum(ordered[:3])<=Decimal('.8')+tolerance,
            MINIMUM_EFFECTIVE_N=effective>=Decimal(len(ordered))*Decimal('.7')-tolerance,
            RISK_CHAIN_TOP1_WEIGHT=max(chains.values())<=Decimal('.55')+tolerance)
    if not exact(checks,result['declared_constraint_checks']) or result['declared_constraints_passed'] is not all(checks.values()):raise ValueError('Independent Decimal five-risk verdict differs')
    projection=result['projection_reconstruction_audit']
    if projection['schema']!='ndx_projection_reconstruction_audit_v1' or projection['promotion_allowed'] is not False or projection['prior_results_reused'] is not False or type(projection['attempt_count']) is not int or projection['attempt_count']!=len(projection['attempts']):raise ValueError('Projection audit diagnostic scope differs')
    return dict(task_id=task['task_id'],weight_spec=task['weight_spec'],holding_count=len(sids),issuer_count=len(sids),
        fit_data_sha256=digest(payload),weights={s:str(v) for s,v in weights.items()},decimal_weight_sum=str(total),decimal_effective_n=str(effective),
        five_risk_checks=checks,risk_pass=all(checks.values()),risk_failures=[k for k,v in checks.items() if not v],
        equal_weight_exact_verified=task['weight_spec']=='equal_weight',constrained_projection_optimality_independently_verified=False)


def build(index_path,index_sha256,*,completed_prefix_confirmed=False):
    if completed_prefix_confirmed is not True:raise ValueError('Require caller-confirmed completed bounded-run prefix; never discover a running index')
    sources=dict(LOADED);sources[str(OWNER)]=OWNER_SHA
    plan=read(dict(path=str(PLAN),sha256=PLAN_SHA),sources)
    if any(plan[k] is not False for k in FALSE):raise ValueError('Plan scope differs')
    archive.merge(sources,plan['historical_expected_source_hashes'])
    document=read(plan['panel_reference'],sources);panel=document['panel'];canonical=inspect_plan(plan,panel)
    indexref=dict(path=str(Path(index_path).resolve()),sha256=index_sha256);index=read(indexref,sources)
    entries=index['entries'];completed=len(entries);folder=Path(index['output_directory']).resolve()
    expected=dict(schema='LATEST_ALL_K_BOUNDED_INDEX_V1',plan_reference=dict(path=str(PLAN),sha256=PLAN_SHA),output_directory=str(folder),planned=764,
        completed=completed,status='COMPLETE' if completed==764 else 'PARTIAL',entries=entries,**dict.fromkeys(FALSE,False))
    if not exact(index,expected) or not 1<=completed<=764 or [e['task_id'] for e in entries]!=[t['task_id'] for t in plan['canonical_tasks'][:completed]]:raise ValueError('Exact nonempty completed canonical prefix required')
    expected_numerical=numerical_sources._sources() # source closure only; no numerical evaluator call
    contract=archive.load_contract()
    archive.merge(sources,expected_numerical);archive.verify_expected_sources(sources,contract)
    details=[]
    for entry in entries:
        task=canonical[entry['task_id']];path=folder/(task['task_id']+'.json');marker=Path(str(path)+'.started.json')
        if set(entry)!={'task_id','path','sha256','started_sha256'} or entry['path']!=str(path):raise ValueError('Exact task checkpoint address required')
        value=read(dict(path=str(path),sha256=entry['sha256']),sources)
        started=read(dict(path=str(marker),sha256=entry['started_sha256']),sources)
        if not exact(started,dict(schema='LATEST_ALL_K_SINGLE_ATTEMPT_V1',plan_sha256=PLAN_SHA,task_id=task['task_id'],attempt_count=1)):raise ValueError('Exclusive attempt identity differs')
        if value['schema']!='LATEST_CONDITIONAL_ALL_K_SINGLE_REFIT_V1' or not exact(value['task'],task) or value['plan_reference']!=expected['plan_reference'] or type(value['attempt_count']) is not int or value['attempt_count']!=1 or any(value[k] is not False for k in FALSE):raise ValueError('Saved task scope/identity differs')
        result=value['result']
        if not exact(result['source_hashes'],expected_numerical):raise ValueError('Original numerical source closure differs')
        required=dict(plan['historical_expected_source_hashes']);archive.merge(required,{str(PLAN):PLAN_SHA,str(marker):entry['started_sha256']})
        if any(value['historical_expected_source_hashes'].get(p)!=h for p,h in required.items()):raise ValueError('Task source omitted or re-signed')
        if not exact(declared_partition(value['historical_expected_source_hashes'],contract),value['archive_resolution']):raise ValueError('Saved archive provenance differs')
        archive.merge(sources,value['historical_expected_source_hashes']);detail=inspect_result(result,task,panel)
        if value['status']!=('FITTED_ORIGINAL_FIVE_RISKS_PASSED' if detail['risk_pass'] else 'FITTED_ORIGINAL_FIVE_RISKS_FAILED'):raise ValueError('Saved status differs from risk checks')
        detail['checkpoint_reference']=dict(path=str(path),sha256=entry['sha256']);details.append(detail)
    partition=archive.verify_expected_sources(sources,archive.load_contract())
    return dict(schema='LATEST_ALL_K_COMPLETED_PREFIX_INDEPENDENT_AUDIT_V1',plan_reference=expected['plan_reference'],index_reference=indexref,
        prefix_completion_evidence='CALLER_OBSERVED_BOUNDED_RUN_EXIT_NOT_INDEPENDENT_PROCESS_ATTESTATION',planned=764,completed=completed,
        pending=764-completed,alias_count=382,aliases_independently_fitted=0,alias_equivalence_verified=False,
        details=details,risk_pass_count=sum(d['risk_pass'] for d in details),risk_fail_count=sum(not d['risk_pass'] for d in details),
        completed_weight_specs=dict(Counter(d['weight_spec'] for d in details)),all_original_126_matrices_verified=True,
        all_seven_parameters_and_five_risks_verified=True,solver_called=False,owner_check_result_called=False,
        risk_boundary_policy='DECIMAL_AT_ORIGINAL_1E_MINUS9_TOLERANCE_DISAGREEMENT_WITH_SAVED_BINARYFLOAT_VERDICT_FAILS_CLOSED_NO_RESIGNING',
        constrained_projection_optimality_independently_verified=False,historical_expected_source_hashes=sources,archive_resolution=partition,**dict.fromkeys(FALSE,False))


def publish_verified(path,value):
    sources=value['historical_expected_source_hashes']
    if any(sources.get(p)!=h for p,h in LOADED.items()):raise ValueError('Audit source omitted')
    if archive.verify_expected_sources(sources,archive.load_contract())!=value['archive_resolution']:raise ValueError('Source drift')
    result=exclusive_publish(path,value)
    if archive.verify_expected_sources(sources,archive.load_contract())!=value['archive_resolution']:raise ValueError('Source drift after publication')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--index',required=True);parser.add_argument('--index-sha256',required=True);parser.add_argument('--completed-prefix-confirmed',action='store_true');parser.add_argument('--output',required=True)
    args=parser.parse_args();print(json.dumps(publish_verified(args.output,build(args.index,args.index_sha256,completed_prefix_confirmed=args.completed_prefix_confirmed))))
