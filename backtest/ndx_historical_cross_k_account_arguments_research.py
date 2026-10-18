"""Bind one historical fit to candidate-account inputs; never fits or executes."""
from copy import deepcopy
import hashlib
import json
from backtest import ndx_conditional_single_window_account_arguments_research as assembly
from backtest import ndx_frozen_target_normalization_audit_research as normalization
from backtest import ndx_frozen_accounting_independent_audit_research as accounting
from scripts import ndx_latest_all_k_completed_independent_audit_20260919 as scalar
from scripts import ndx_fourteen_incremental_independent_audit_20260919 as shape


def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def exact(a,b):return digest(a)==digest(b)


def first_window(inputs):
    prices=inputs['prices'];dates=prices['calendar'];encoded=deepcopy(prices['returns'])
    if inputs['schema']!='SOURCE_BOUND_TWENTY_CONDITIONAL_HISTORICAL_INPUTS_V1' or len(dates)!=253 or dates[126]!='2026-03-18' or dates[127]!='2026-03-19' or dates[-1]!='2026-09-17' or encoded['index']!=[d+'T00:00:00' for d in dates[1:]] or len(encoded['data'])!=252:raise ValueError('Original historical 253-price/252-return clock required')
    if prices['fit_return_dates']!=dates[1:127] or prices['evaluation_return_dates']!=dates[127:]:raise ValueError('Historical fit/forward windows differ')
    encoded['index']=encoded['index'][:126];encoded['data']=encoded['data'][:126]
    return encoded


def prepare_candidate_arguments(*,inputs,task,result,numerical_sources,audited_detail):
    """External artifacts must be authenticated separately before execution."""
    task=deepcopy(task);result=deepcopy(result)
    if set(task)!={'task_id','selected','holding_count','weight_spec','cutoff','parameters','previous_target_weights'} or task['task_id']!=digest({k:v for k,v in task.items() if k!='task_id'}) or task['cutoff']!='2026-03-18' or task['previous_target_weights'] is not None or not exact(task['parameters'],scalar.PARAMS):raise ValueError('Exact historical task and original parameters required')
    selected=task['selected'];rows=inputs['candidate_coordinate_and_risk_rows'];coordinates={r['security_id']:r for r in rows}
    if len(rows)!=14 or len(coordinates)!=14 or type(task['holding_count']) is not int or task['holding_count']!=len(selected) or not 1<=len(selected)<=14 or not set(selected)<=set(coordinates):raise ValueError('Explicit dynamic subset of fourteen required')
    if len({v['issuer_id'] for v in selected.values()})!=len(selected):raise ValueError('One security per issuer required')
    if not exact(selected,{s:{k:coordinates[s][k] for k in ('ticker','issuer_id','risk_chain')} for s in selected}):raise ValueError('Historical selected coordinate differs from source assumptions')
    if not numerical_sources or not exact(result['source_hashes'],numerical_sources):raise ValueError('Original numerical closure required')
    shape.result_schema(result,task)
    detail=scalar.inspect_result(result,task,dict(returns=first_window(inputs)))
    if not exact(detail,audited_detail):raise ValueError('External independent numerical detail differs')
    failures=[k for k,v in detail['five_risk_checks'].items() if not v]
    shared=dict(schema='HISTORICAL_CROSS_K_CANDIDATE_ACCOUNT_BINDING_V1',task_id=task['task_id'],task=task,
        fit_matrix_sha256=detail['fit_data_sha256'],independent_numerical_detail=detail,failed_original_risk_checks=failures,
        original_risk_parameters=deepcopy(task['parameters']),external_source_bytes_authenticated=False,
        execution_performed=False,fit_performed=False,result_reused=False,control_executed=False,
        order_acceptance_proven=False,all_ndx_legal_pool_verified=False,historical_identity_interval_verified=False,
        point_in_time_verified=False,promotion_allowed=False,winner_selected=False)
    if failures:
        return dict(shared,status='NOT_EXECUTED_ORIGINAL_FIVE_RISK_FAILURE',account=None,normalization_evidence=None)
    schedule=[dict(decision_date='2026-03-18',execution_date='2026-03-19',targets=deepcopy(result['targets']))]
    risks={'2026-03-18':deepcopy(result['risk_chains_by_security'])}
    arguments=assembly.assemble_account_arguments(inputs=inputs,schedule=schedule,risk_chains_by_decision=risks)
    effective,evidence=normalization.normalized_schedule(schedule)
    candidate=arguments['candidate']
    account=dict(calendar=arguments['calendar'],contract=arguments['contract'],selected=candidate,
        effective_schedule=effective,scope='CONDITIONAL_HISTORICAL_CANDIDATE_NO_ORDER_ACCEPTANCE_CLAIM')
    return dict(shared,status='READY_FOR_SOURCE_BOUND_SINGLE_ATTEMPT',account=account,normalization_evidence=evidence)


def existing_account_equivalence(prepared,saved,*,source_input_reference):
    """Numerical reuse precondition, not authentication or an actual import."""
    if prepared['status']!='READY_FOR_SOURCE_BOUND_SINGLE_ATTEMPT' or saved['schema']!='HISTORICAL_SINGLE_WINDOW_CONDITIONAL_ACCOUNT_V1' or saved['track']!='candidate':raise ValueError('Only independently checked candidate paths may be compared')
    if set(source_input_reference)!={'path','sha256'} or not exact(saved['input_reference'],source_input_reference):raise ValueError('Explicit common source-input reference required')
    account=prepared['account'];selected=account['selected']
    for key,expected in dict(calendar=account['calendar'],schedule=selected['original_schedule'],effective_schedule=account['effective_schedule'],normalization_evidence=prepared['normalization_evidence'],execution_contract=account['contract'],internal_columns=selected['columns']).items():
        if not exact(saved[key],expected):raise ValueError('Saved account clock/target/fees/normalization differs')
    if saved['risk_is_order_gate'] is not True or saved['execution_performed'] is not True or any(saved[k] is not False for k in ('fit_performed','point_in_time_verified','legal_training_input_admitted','promotion_allowed','winner_selected','provider_identity_verified','continuous_identity_interval_verified','corporate_action_completeness_verified','cash_dividends_modelled','additional_cash_flows_supported')):raise ValueError('Conditional account scope differs')
    checked=accounting.audit(execution=saved['execution'],calendar=account['calendar'],schedule=account['effective_schedule'],prices=selected['prices'],risk_chains_by_decision=selected['arguments']['risk_chains_by_decision'],contract=account['contract'])
    if not exact(checked,saved['independent_decimal_accounting']):raise ValueError('Existing independent accounting result differs')
    return dict(account_arguments_and_ledger_match_under_declared_input_reference=True,external_raw_and_marker_authenticated=False,
        external_source_bytes_authenticated=False,result_reused=False,engine_called=False,point_in_time_verified=False,promotion_allowed=False)
