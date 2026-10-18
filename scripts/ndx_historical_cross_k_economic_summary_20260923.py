"""Read-only economic inventory of a hard independently audited account prefix."""
import argparse
import hashlib
import json
import sys
from collections import Counter
from decimal import Decimal, localcontext
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backtest import ndx_root_price_archive_contract_research as archive
from scripts.ndx_corrected_frontier_single_refit_archive_research import publish

AUDIT = ROOT / 'data/cache/research/historical_cross_k_candidate_accounts_20260923_v1/completed_101_independent_audit.json'
AUDIT_SHA = '9ba66d3223620236c7638b34efc3ce8de9d5239eee57c8c81e1252996c3f5582'
FALSE = ('engine_called', 'fit_performed', 'ledger_audit_repeated', 'winner_selected',
    'promotion_allowed', 'formal_dual_benchmark_admission', 'point_in_time_verified',
    'future_one_year_oos_evaluation_performed', 'legal_training_input_admitted',
    'full_all_ndx_pool_covered', 'currency_fx_equivalence_verified', 'nav_publication_time_verified',
    'corporate_action_completeness_verified', 'external_account_imported')
METRICS = ('path_return', 'path_max_drawdown', 'annualized_return_252_over_126')


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def canonical(v): return json.dumps(v, sort_keys=True, separators=(',', ':'), allow_nan=False)
LOADED = {str(p):sha(p) for p in (Path(__file__).resolve(), archive.SOURCE, archive.drift.SOURCE, Path(publish.__code__.co_filename).resolve())}


def number(v):
    if type(v) is not str:
        raise ValueError('Audited decimal string required')
    value = Decimal(v)
    if not value.is_finite(): raise ValueError('Finite audited decimal required')
    return value


def read(ref, sources):
    if set(ref) != {'path','sha256'} or not Path(ref['path']).is_absolute():
        raise ValueError('Exact absolute external reference required')
    raw = Path(ref['path']).read_bytes()
    if hashlib.sha256(raw).hexdigest() != ref['sha256']: raise ValueError('Artifact hash differs')
    archive.merge(sources, {ref['path']:ref['sha256']})
    return json.loads(raw)


def explain(execution):
    decisions=execution['decisions']; fills=execution['executions']; trades=execution['trades']
    if len(decisions)!=1 or len(fills)>1: raise ValueError('Single historical decision expected')
    decision=decisions[0]; status=decision['status']
    if status=='NO_PLAN':
        if fills or trades: raise ValueError('NO_PLAN must have no fill or trade')
        outcome='NO_PLAN'
        reason='FROZEN_ENGINE_REPORTED_NO_PLAN_NOT_PROOF_OF_GLOBAL_INTEGER_INFEASIBILITY'
    elif status=='FROZEN' and len(fills)==1 and fills[0]['status'] in ('FILLED','REJECTED'):
        outcome=fills[0]['status']
        if outcome=='REJECTED' and trades: raise ValueError('Rejected atomic order cannot have trades')
        reason='RECORDED_OPEN_REJECTION_REASONS' if outcome=='REJECTED' else ('FILLED_WITH_TRADES' if trades else 'FILLED_ZERO_DELTA_NO_TRADES')
    else: raise ValueError('Unrecognized decision/execution path')
    projection=decision.get('projection')
    return dict(outcome=outcome, reason=reason, trade_count=len(trades),
        rejection_reasons=fills[0].get('failure_reasons',[]) if fills else [],
        decision_status=status, projection_status=projection.get('status') if projection else None,
        full_integer_infeasibility_proven=False,
        actual_holding_count_last_session=sum(v>0 for v in execution['daily'][-1]['shares'].values()),
        all_cash_last_session=not any(v>0 for v in execution['daily'][-1]['shares'].values()))


def summarize_detail(detail, saved, raw):
    task_id=detail['task_id']; independent=detail['independent_result']
    if saved['task_id']!=task_id or independent['task_id']!=task_id or saved['status']!=detail['status']:
        raise ValueError('Exact task linkage required')
    if canonical(saved['raw_reference'])!=canonical(detail['raw_reference']) or canonical(saved['fit_checkpoint_reference'])!=canonical(detail['fit_checkpoint_reference']):
        raise ValueError('Exact raw and historical fit references required')
    row=dict(task_id=task_id, target_k=detail['holding_count'], weight_spec=detail['weight_spec'],
        result_reference=detail['result_reference'], raw_reference=detail['raw_reference'],
        fit_checkpoint_reference=detail['fit_checkpoint_reference'], failed_original_risk_checks=saved['failed_original_risk_checks'])
    if detail['status']=='SKIPPED_RISK':
        if raw is not None or saved['execution'] is not None or not row['failed_original_risk_checks']:
            raise ValueError('Skipped risk must retain failure without execution')
        return dict(row,outcome='SKIPPED_RISK',reason='ORIGINAL_FIVE_RISK_FAILURE',metrics=None,pareto_coordinates=None)
    if raw is None or raw['task_id']!=task_id or raw['parameter_digest']!=saved['parameter_digest'] or raw['execution_performed'] is not True:
        raise ValueError('Bound original raw receipt required')
    if saved['execution_performed'] is not True or row['failed_original_risk_checks']:
        raise ValueError('Executed risk-qualified result required')
    comparison=independent['comparison']; metrics=comparison['candidate']
    calendar=saved['arguments']['calendar']
    if comparison['calendar']!=calendar or len(calendar)!=127 or calendar[0]!='2026-03-18' or calendar[-1]!='2026-09-17':
        raise ValueError('Exact shared historical clock required')
    for name in ('currency_fx_equivalence_verified','formal_dual_benchmark_admission','future_one_year_oos_evaluation_performed','point_in_time_verified','promotion_allowed','winner_selected'):
        if comparison[name] is not False: raise ValueError('Original comparison limitation upgraded')
    if metrics['observation_count']!=127 or type(metrics['observation_count']) is not int or metrics['return_interval_count']!=126 or type(metrics['return_interval_count']) is not int:
        raise ValueError('Exact metric clock denominator required')
    for key in METRICS: number(metrics[key])
    differences={}; coordinates=[]
    with localcontext() as ctx:
        ctx.prec=80
        for name in ('original_incumbent','nav_012922_native_currency'):
            reference=comparison['references'][name]
            differences[name]={k:str(number(metrics[k])-number(reference[k])) for k in METRICS}
            coordinates.extend([differences[name]['path_return'],str(-number(differences[name]['path_max_drawdown']))])
    explanation=explain(saved['execution'])
    weights=independent['independent_fit_detail']['weights']
    if len(weights)!=row['target_k']: raise ValueError('Target k and audited weights differ')
    return dict(row,**explanation, original_target_weights=weights,
        original_schedule=saved['arguments']['schedule'], effective_schedule=saved['arguments']['effective_schedule'],
        metrics=metrics, benchmark_metrics=comparison['references'],
        candidate_minus_benchmark=differences, pareto_coordinates=coordinates,
        audited_fees_usd=independent['candidate_accounting']['fees_usd'],
        metric_source='EXISTING_HARD_INDEPENDENT_LEDGER_AUDIT_NOT_RECOMPUTED_LEDGER')


def pareto(rows):
    eligible=[r for r in rows if r['pareto_coordinates'] is not None]
    values=[[number(x) for x in row['pareto_coordinates']] for row in eligible]
    return [row['task_id'] for i,row in enumerate(eligible) if not any(
        all(a>=b for a,b in zip(other,values[i],strict=True)) and any(a>b for a,b in zip(other,values[i],strict=True))
        for j,other in enumerate(values) if i!=j)]


def aggregate(rows, expected_count):
    if type(expected_count) is not int or len(rows)!=expected_count or len({r['task_id'] for r in rows})!=expected_count:
        raise ValueError('Complete unique independently audited denominator required')
    reference=None
    for row in rows:
        if row['metrics'] is not None:
            if reference is None: reference=row['benchmark_metrics']
            if canonical(reference)!=canonical(row['benchmark_metrics']): raise ValueError('Shared benchmark metrics differ')
    return dict(completed_account_count=len(rows),outcome_counts=dict(Counter(r['outcome'] for r in rows)),
        by_target_k=[dict(target_k=k,count=sum(r['target_k']==k for r in rows),outcomes=dict(Counter(r['outcome'] for r in rows if r['target_k']==k))) for k in sorted({r['target_k'] for r in rows})],
        benchmark_metrics=reference,all_account_pareto_task_ids=pareto(rows),
        filled_account_pareto_task_ids=pareto([r for r in rows if r['outcome']=='FILLED']),
        pareto_axes=['RETURN_MINUS_INCUMBENT_MAX','NEGATIVE_DD_DIFFERENCE_INCUMBENT_MAX','RETURN_MINUS_NATIVE_NAV_MAX','NEGATIVE_DD_DIFFERENCE_NATIVE_NAV_MAX'],
        exact_decimal_ties_all_retained=True, cash_paths_retained_in_all_account_frontier=True,
        rows=rows, **dict.fromkeys(FALSE,False))


def build(audit_path=AUDIT,audit_sha256=AUDIT_SHA):
    if str(Path(audit_path).resolve())!=str(AUDIT) or audit_sha256!=AUDIT_SHA:
        raise ValueError('This inventory is bound to the independently audited 101 prefix')
    sources=dict(LOADED); reference=dict(path=str(AUDIT),sha256=AUDIT_SHA); audit=read(reference,sources)
    if audit['schema']!='HISTORICAL_CROSS_K_ACCOUNT_PREFIX_INDEPENDENT_AUDIT_V1' or audit['completed_account_task_count']!=101 or type(audit['completed_account_task_count']) is not int or audit['raw_marker_result_chain_verified'] is not True:
        raise ValueError('Complete sealed account audit required')
    contract=archive.load_contract()
    if canonical(archive.verify_expected_sources(audit['historical_expected_source_hashes'],contract))!=canonical(audit['archive_resolution']):
        raise ValueError('Original audit source partition differs')
    archive.merge(sources,audit['historical_expected_source_hashes'])
    index=read(audit['index_reference'],sources)
    if index['finalized_after_full_source_verification'] is not True or [e['task_id'] for e in index['entries']]!=[d['task_id'] for d in audit['details']]:
        raise ValueError('Finalized complete index and audit order differ')
    rows=[]
    for entry, detail in zip(index['entries'],audit['details'],strict=True):
        for key in ('result_reference','raw_reference'):
            if canonical(entry[key])!=canonical(detail[key]): raise ValueError('Audit artifact linkage differs')
        saved=read(detail['result_reference'],sources)
        raw=read(detail['raw_reference'],sources) if detail['raw_reference'] else None
        read(entry['started_reference'],sources)
        if saved['started_reference']!=entry['started_reference']: raise ValueError('Marker reference differs')
        if any(sources.get(p)!=h for p,h in saved['historical_expected_source_hashes'].items()): raise ValueError('Checkpoint source omitted from audited closure')
        rows.append(summarize_detail(detail,saved,raw))
    result=aggregate(rows,101)
    return dict(result,schema='HISTORICAL_CROSS_K_101_ACCOUNT_ECONOMIC_SUMMARY_V1',
        audit_reference=reference,index_reference=audit['index_reference'],plan_reference=audit['plan_reference'],
        historical_plan_canonical_task_count=31828,new_historical_fit_task_count=31827,
        summarized_new_account_count=101, unsummarized_new_account_count=31827-101,
        external_mechanical_account_reference=audit['external_completed_account_reference'],external_mechanical_account_included_in_101=False,
        shared_control_reference=audit['shared_control_reference'],shared_comparison_reference=audit['shared_comparison_reference'],
        scope='AUDITED_HISTORICAL_14_CONDITIONAL_SUBSET_PREFIX_NOT_ALL_NDX_OR_FULL_CROSS_K_DELIVERY',
        nav_currency_policy='ORIGINAL_CURRENCY_DIAGNOSTIC_NO_FX_OR_PUBLICATION_TIME_EQUIVALENCE',
        historical_expected_source_hashes=sources,archive_resolution=archive.verify_expected_sources(sources,contract))


def verify(value):
    if canonical(value)!=canonical(build()): raise ValueError('Complete economic summary rebuild differs')


def publish_verified(path,value):
    verify(value); reference=publish(path,value)
    if canonical(archive.verify_expected_sources(value['historical_expected_source_hashes'],archive.load_contract()))!=canonical(value['archive_resolution']):
        raise ValueError('Sources changed after publication')
    return reference


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);args=parser.parse_args()
    print(json.dumps(publish_verified(args.output,build())))
