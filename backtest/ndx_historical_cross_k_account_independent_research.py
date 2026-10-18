"""Pure independent per-task account readback; no producer, engine, fit or I/O."""
from copy import deepcopy
import hashlib
import json
from backtest import ndx_frozen_accounting_independent_audit_research as candidate_oracle
from backtest import ndx_fixed_control_accounting_independent_audit_v2_research as control_oracle
from backtest import ndx_frozen_target_normalization_audit_research as normalization
from backtest import ndx_single_window_benchmark_metrics_research as metrics
from scripts import ndx_latest_all_k_completed_independent_audit_20260919 as scalar
from scripts import ndx_fourteen_incremental_independent_audit_20260919 as shape

CONTRACT=dict(initial_cash_usd=25000,minimum_cash_buffer_usd=100,transaction_cost_bps=10,
    max_single_weight=.45,min_single_weight=.05,top_weight_cap=.8,minimum_effective_n_ratio=.7,risk_chain_top1_cap=.55)
FALSE=('source_bytes_authenticated','external_fit_audit_authenticated','original_control_source_authenticated','engine_called','fitter_called',
    'winner_selected','all_ndx_legal_pool_verified','historical_identity_interval_verified','historical_risk_qualification_verified',
    'point_in_time_verified','promotion_allowed','execution_replayed','constrained_projection_optimality_independently_verified')


def exact(a,b):return json.dumps(a,sort_keys=True,allow_nan=False)==json.dumps(b,sort_keys=True,allow_nan=False)
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def task_view(inputs,task,result,numerical_sources,audited_detail):
    if inputs['schema']!='SOURCE_BOUND_TWENTY_CONDITIONAL_HISTORICAL_INPUTS_V1' or any(inputs[k] is not False for k in ('fit_performed','execution_performed','point_in_time_verified','legal_training_input_admitted','promotion_allowed','latest_weights_backfilled')):raise ValueError('Conditional source input scope required')
    if set(task)!={'task_id','selected','holding_count','weight_spec','cutoff','parameters','previous_target_weights'} or task['task_id']!=digest({k:v for k,v in task.items() if k!='task_id'}) or task['cutoff']!='2026-03-18' or task['previous_target_weights'] is not None or not exact(task['parameters'],scalar.PARAMS):raise ValueError('Original historical task identity and parameters required')
    rows=inputs['candidate_coordinate_and_risk_rows'];coordinates={r['security_id']:r for r in rows};selected=task['selected']
    if len(rows)!=14 or len(coordinates)!=14 or type(task['holding_count']) is not int or task['holding_count']!=len(selected) or not 1<=len(selected)<=14 or not set(selected)<=set(coordinates):raise ValueError('Dynamic conditional task subset required')
    if not exact(selected,{s:{k:coordinates[s][k] for k in ('ticker','issuer_id','risk_chain')} for s in selected}) or len({r['issuer_id'] for r in selected.values()})!=len(selected):raise ValueError('Exact selected security/issuer/channel/risk mapping required')
    prices=inputs['prices'];dates=prices['calendar'];frame=deepcopy(prices['returns'])
    if len(dates)!=253 or dates[126]!='2026-03-18' or dates[127]!='2026-03-19' or dates[-1]!='2026-09-17' or frame['index']!=[d+'T00:00:00' for d in dates[1:]] or len(frame['data'])!=252 or prices['fit_return_dates']!=dates[1:127] or prices['evaluation_return_dates']!=dates[127:]:raise ValueError('Exact first126 historical matrix/forward clock required')
    frame['index']=frame['index'][:126];frame['data']=frame['data'][:126]
    shape.result_schema(result,task)
    if not numerical_sources or not exact(result['source_hashes'],numerical_sources):raise ValueError('Frozen numerical source declarations differ')
    detail=scalar.inspect_result(result,task,dict(returns=frame))
    if not exact(detail,audited_detail):raise ValueError('Supplied independent fit detail differs')
    return detail,dates[126:],{s:coordinates[s] for s in selected}


def marks(inputs,calendar,labels):
    full=inputs['prices']['calendar'];result={d:{} for d in calendar}
    for field in ('open','close'):
        frame=inputs['prices']['nominal_'+field]
        if frame['type']!='dataframe' or frame['index_kind']!='DatetimeIndex' or frame['index']!=[d+'T00:00:00' for d in full] or len(frame['columns'])!=20 or len(set(frame['columns']))!=20 or frame['dtypes']!=['float64']*20 or len(frame['data'])!=253:raise ValueError('Complete nominal Open/Close typed matrices required')
        positions={s:frame['columns'].index(r['ticker']) for s,r in labels.items()}
        for i,day in enumerate(calendar,126):
            if len(frame['data'][i])!=20:raise ValueError('Incomplete price row')
            for sid,row in labels.items():
                value=frame['data'][i][positions[sid]]
                if type(value) is not float or candidate_oracle.number(value)<=0:raise ValueError('Positive finite float64 nominal marks required')
                result[day].setdefault(sid,dict(ticker=row['ticker']))[field]=value
    return result


def restore_only_labels(raw,labels):
    value=deepcopy(raw);columns={s:'SID_'+s.upper().replace(':','_') for s in labels}
    for decision in value['decisions']:
        for sid,row in decision['targets'].items():
            if row['ticker']!=columns[sid]:raise ValueError('Raw decision stable column differs')
            row['ticker']=labels[sid]['ticker']
    for row in value['trades']:
        sid=row['security_id']
        if row['ticker']!=columns[sid]:raise ValueError('Raw trade stable column differs')
        row['ticker']=labels[sid]['ticker']
    for row in value['daily']:
        if row['tickers']!={s:columns[s] for s in row['shares']}:raise ValueError('Raw daily stable columns differ')
        row['tickers']={s:labels[s]['ticker'] for s in row['shares']}
    return value


def audit_candidate(*,inputs,task,result,numerical_sources,audited_detail,raw_execution,execution,
                    effective_schedule,normalization_evidence,control_execution=None,nav_csv=None):
    """All arguments are untrusted declarations until a separate I/O reader binds them."""
    detail,calendar,labels=task_view(inputs,task,result,numerical_sources,audited_detail)
    shared=dict(schema='HISTORICAL_CROSS_K_ACCOUNT_INDEPENDENT_RESEARCH_V1',task_id=task['task_id'],holding_count=len(labels),
        independent_fit_detail=detail,failed_original_risk_checks=detail['risk_failures'],**dict.fromkeys(FALSE,False))
    if not detail['risk_pass']:
        if any(v is not None for v in (raw_execution,execution,effective_schedule,normalization_evidence)):raise ValueError('Risk-failed task cannot carry an executed account')
        return dict(shared,status='NOT_EXECUTED_ORIGINAL_FIVE_RISK_FAILURE',candidate_accounting=None,control_accounting=None,comparison=None)
    metrics.check_calendar(calendar)
    if inputs['prices']['known_evaluation_split_events']!=[] or inputs['prices']['cash_dividends_included'] is not False:raise ValueError('Action-free nominal execution window required')
    for events in inputs['prices']['submitted_full_split_events'].values():
        if any(calendar[0]<r['session']<=calendar[-1] for r in events):raise ValueError('Known action inside execution window')
    original=[dict(decision_date=calendar[0],execution_date=calendar[1],targets=deepcopy(result['targets']))]
    effective,evidence=normalization.normalized_schedule(original)
    if not exact(effective_schedule,effective) or not exact(normalization_evidence,evidence):raise ValueError('Exact one-time normalization required')
    if not exact(restore_only_labels(raw_execution,labels),execution):raise ValueError('Account altered raw receipt beyond ticker labels')
    chains={calendar[0]:{s:labels[s]['risk_chain'] for s in labels}}
    candidate=candidate_oracle.audit(execution=execution,calendar=calendar,schedule=effective,prices=marks(inputs,calendar,labels),risk_chains_by_decision=chains,contract=CONTRACT)
    control_rows=inputs['incumbent_original_securities'];control_labels={r['security_id']:r for r in control_rows}
    if len(control_rows)!=8 or len(control_labels)!=8 or len({r['issuer_id'] for r in control_rows})!=8 or {r['ticker'] for r in control_rows}!={'NVDA','TXN','ASML','CDNS','TSM','MU','MSFT','GOOG'}:raise ValueError('Original eight reference denominator required')
    candidate_by_ticker={r['ticker']:r for r in inputs['candidate_coordinate_and_risk_rows']}
    for row in control_rows:
        shared_row=candidate_by_ticker.get(row['ticker'])
        if shared_row is not None and any(shared_row[k]!=row[k] for k in ('security_id','issuer_id','risk_chain')):raise ValueError('Shared candidate/control coordinate conflict')
    control_schedule=[dict(decision_date=calendar[0],execution_date=calendar[1],targets={s:{k:r[k] for k in ('ticker','issuer_id','target_weight')} for s,r in control_labels.items()})]
    control=control_oracle.audit(execution=control_execution,calendar=calendar,schedule=control_schedule,prices=marks(inputs,calendar,control_labels),
        risk_chains_by_decision={calendar[0]:{s:r['risk_chain'] for s,r in control_labels.items()}},contract=CONTRACT)
    compared=metrics.compare(calendar=calendar,candidate_daily=execution['daily'],incumbent_daily=control_execution['daily'],nav_csv=nav_csv)
    return dict(shared,status='SAVED_ACCOUNT_INDEPENDENTLY_CHECKED_NOT_ADMISSION',candidate_accounting=candidate,control_accounting=control,comparison=compared)
