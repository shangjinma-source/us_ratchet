"""Complete corrected researched-subpool competition, using unchanged economic kernels."""
from collections import Counter
from copy import deepcopy
import hashlib,json,math
from pathlib import Path
import numpy as np
from backtest import ndx_combined_fractional_frontier_research as previous
from backtest import ndx_fractional_research_gates as gates
from backtest import ndx_dynamic_envelope_policy as envelope
SOURCE=Path(__file__).resolve()
LOADED={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (SOURCE,Path(previous.__file__).resolve(),Path(gates.__file__).resolve(),Path(envelope.__file__).resolve())}
ORIGINS=('EQUAL_WEIGHT_BASE','NON_EQUAL_BASE','DELTA')
FLAGS=('historical_full_source_closure_verified','point_in_time_verified','promotion_allowed','selection_performed')
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def verify_sources():
    for p,h in LOADED.items():
        if hashlib.sha256(Path(p).read_bytes()).hexdigest()!=h:raise ValueError('Loaded economic source changed')
def analyze_complete_corrected_date(*,complete_overlay,original_parent,original_training_semantics,delta_contracts):
    verify_sources();complete=complete_overlay;parent=original_parent
    if complete.get('schema')!='ndx_selected_complete_date_overlay_v1' or parent.get('schema') not in ('ndx_corrected_delta_paired_overlay_limited_drift_v2','ndx_corrected_base_overlay_limited_drift_v3'):raise ValueError('Complete corrected date and final original parent required')
    for doc in (complete,parent):
        if any(doc.get(k) is not False for k in FLAGS) or doc.get('winner') is not None or doc.get('scope')!='ORIGINAL_RESEARCHED_SUBPOOL_NOT_FULL_NDX':raise ValueError('Original researched subpool scope required')
        if digest(doc['records'])!=doc['records_sha256']:raise ValueError('Full records digest differs')
    if (complete.get('economic_inputs_complete') is not True or type(complete.get('pending_count')) is not int or complete['pending_count']!=0
        or type(complete.get('original_count')) is not int or complete['original_count']!=parent['original_count']
        or complete.get('available_count')!=complete['original_count'] or len(complete['records'])!=complete['original_count']
        or digest(complete['coordinate'])!=digest(parent['coordinate'])):raise ValueError('Complete one-date denominator required')
    semantics=original_training_semantics;payload=semantics['payload'];signature=semantics['training_semantics_sha256']
    if (digest(payload)!=signature or payload.get('schema')!='ndx_dynamic_training_semantics_v1'
        or any(payload[k]!=parent['coordinate'][k] for k in ('source_batch','universe_track'))):raise ValueError('Bound original training contract differs')
    originals={};definitions=set();rows=[];seen=set();counts=Counter();replaced=0;missing_semantics=0
    delta_jobs={r['task']['job_id'] for r in parent['records'] if r['origin']=='DELTA'}
    if set(delta_contracts)!=delta_jobs or any(digest(c)!=digest(payload['contract']) for c in delta_contracts.values()):raise ValueError('Every original DELTA full contract must match bound BASE contract')
    for record in parent['records']:
        key=record['overlay_record_id']
        if key in originals:raise ValueError('Duplicate original record')
        originals[key]=record
    if len(originals)!=parent['original_count']:raise ValueError('Original record denominator differs')
    for record in complete['records']:
        key=record['overlay_record_id'];task=record['task'];metrics=record['result']
        if key in seen or key not in originals:raise ValueError('Duplicate or unexpected corrected record')
        seen.add(key);before=originals[key]
        for field in ('origin','task','original_training_semantics_sha256','correction_signature'):
            if digest(record[field])!=digest(before[field]):raise ValueError('Original full identity or numerical correction changed')
        if record['status']!='AVAILABLE' or type(metrics) is not dict:raise ValueError('Pending or missing metrics cannot compete')
        if before['status']=='AVAILABLE':
            if digest(before)!=digest(record):raise ValueError('Previously available record changed')
        elif before['status']=='PENDING_NUMERICAL_DELTA' and before['origin']=='DELTA' and before['result'] is None:
            if record['overlay_mode']!='SELECTED_DELTA_COMPLETE_DATE':raise ValueError('Missing selected complete-date lineage')
            replaced+=1
        else:raise ValueError('Unknown parent record status')
        origin=record['origin'];counts[origin]+=1
        if origin not in ORIGINS:raise ValueError('Unknown origin')
        observed_signature=record['original_training_semantics_sha256']
        if observed_signature is None and origin=='DELTA':missing_semantics+=1
        elif observed_signature!=signature:raise ValueError('Original semantics differs')
        if any(task[k]!=parent['coordinate'][k] for k in ('source_batch','universe_track','selection_date')) or task['decision_data_end']!=payload['decision_data_end']:raise ValueError('Mixed date or cutoff')
        names=task['tickers'].split(';');k=task['holding_count'];spec=task['weight_spec']
        if type(k) is not int or k!=len(names) or len(set(names))!=k or not all(n and n==n.strip().upper() for n in names):raise ValueError('Explicit unique cardinality required')
        if spec not in ('equal_weight','constrained_fixed_shrinkage','constrained_fixed_shrinkage_turnover_anchor') or (origin=='EQUAL_WEIGHT_BASE' and spec!='equal_weight') or (origin=='NON_EQUAL_BASE' and spec=='equal_weight'):raise ValueError('Original weight/origin contract differs')
        definition=(tuple(sorted(names)),spec)
        if definition in definitions:raise ValueError('Duplicate portfolio definition')
        definitions.add(definition)
        if any(type(metrics.get(field)) is not type(task[field]) or metrics[field]!=task[field] for field in ('tickers','holding_count','weight_spec')):raise ValueError('Metric/task portfolio identity differs')
        checks=gates.fractional_research_gates(metrics=metrics,contract=payload['contract'],holding_count=k)
        absolute={col:previous._number(metrics[col],col) for col in envelope.DIMENSIONS}
        differences={col:previous._number(metrics[col],col) for col in previous.ECONOMIC_COLUMNS}
        if (not absolute['return_p50']>=absolute['return_p10']>=-1 or not 0<=absolute['max_drawdown_p50']<=absolute['max_drawdown_p90']<=1
            or differences['paired_return_p50_vs_incumbent']<differences['paired_return_p10_vs_incumbent']
            or differences['paired_drawdown_cost_p50_vs_incumbent']>differences['paired_drawdown_cost_p90_vs_incumbent']):raise ValueError('Invalid raw/paired quantiles')
        passed={col:differences[col]*float(direction)>=0 for col,direction in zip(previous.ECONOMIC_COLUMNS,previous._DIRECTIONS)}
        fund=all(passed[c] for c in envelope.FUND_COLUMNS.values());inc=all(passed[c] for c in envelope.INCUMBENT_COLUMNS.values())
        rows.append(dict(overlay_record_id=key,job_id=task['job_id'],tickers=task['tickers'],holding_count=k,weight_spec=spec,origin=origin,
            absolute_metrics=absolute,benchmark_differences=differences,dimension_passed=passed,fund_four_dimension_passed=fund,incumbent_four_dimension_passed=inc,dual_benchmark_eight_dimension_passed=fund and inc,
            fractional_risk_passed=checks['fractional_risk_passed'],liquidity_passed=checks['liquidity_passed'],fractional_risk_liquidity_passed=checks['fractional_risk_passed'] and checks['liquidity_passed'],
            failed_benchmark_dimensions=[c for c,v in passed.items() if not v],failed_fractional_checks=[c for c,v in checks['checks'].items() if not v],
            legacy_whole_lot_observation={c:deepcopy(v) for c,v in metrics.items() if c.startswith('whole_lot_')},legacy_whole_lot_used_as_competition_gate=False,
            user_preference_reference=set(names)==envelope.USER_PREFERENCE and spec=='equal_weight'))
    if seen!=set(originals) or len({r['job_id'] for r in rows})!=len(rows) or replaced!=parent['pending_count'] or replaced!=complete['selected_delta_added']:raise ValueError('Complete unchanged task set required')
    for origin in ORIGINS:
        expected=parent['counts'][origin]['planned'];observed=complete['counts'][origin]
        if any(type(x) is not int for x in (expected,observed['planned'],observed['available'],observed['pending'])) or expected!=counts[origin] or observed!=dict(planned=expected,available=expected,pending=0):raise ValueError('Complete origin denominator differs')
    rows.sort(key=lambda r:r['job_id'])
    def frontier(candidates):
        if not candidates:return []
        matrix=np.array([[r['benchmark_differences'][c] for c in previous.ECONOMIC_COLUMNS] for r in candidates])*previous._DIRECTIONS
        return [candidates[i] for i in previous.exact_pareto_indices(matrix)]
    groups=Counter((r['holding_count'],r['origin'],r['weight_spec']) for r in rows)
    output=dict(schema='CORRECTED_COMPLETE_DATE_CROSS_K_FRONTIER_V1',coordinate=deepcopy(parent['coordinate']),original_decision_data_end=payload['decision_data_end'],
        original_training_contract_reference_sha256=signature,corrected_records_sha256=complete['records_sha256'],original_count=len(rows),all_original_records_scanned=True,
        original_delta_semantics_hash_absent_count=missing_semantics,original_delta_full_contracts_checked=True,
        groups=[dict(holding_count=k,origin=o,weight_spec=w,count=n) for (k,o,w),n in sorted(groups.items())],
        candidate_diagnostics=rows,
        raw_frontier=frontier(rows),risk_liquidity_frontier=frontier([r for r in rows if r['fractional_risk_liquidity_passed']]),
        user_preference_references=[r for r in rows if r['user_preference_reference']],economic_columns=list(previous.ECONOMIC_COLUMNS),
        rows_passing_both_benchmarks=sum(r['dual_benchmark_eight_dimension_passed'] for r in rows),
        scope='ORIGINAL_RESEARCHED_SUBPOOL_NOT_FULL_NDX',original_scope_label_is_not_new_membership_approval=True,
        dominance_policy='EXACT_RAW_COMPONENTWISE_NONINFERIOR_AND_ONE_STRICT_IMPROVEMENT_KEEP_ALL_TIES',
        fractional_gate_scope='FOUR_ORIGINAL_CONCENTRATION_CHECKS_PLUS_LIQUIDITY_NOT_FULL_RISK_ADMISSION',
        original_semantics_are_corrected_input_semantics=False,paired_quantiles_are_not_marginal_quantile_differences=True,
        full_ndx_pool_coverage_verified=False,input_artifact_binding_verified=False,whole_lot_status='NOT_EVALUATED',cutoff_refit_required=True,
        original_source_hashes_verified_here=False,source_hashes=dict(LOADED),training_performed=False,execution_performed=False,
        historical_full_source_closure_verified=False,point_in_time_verified=False,promotion_allowed=False,selection_performed=False,winner=None)
    verify_sources();return output
