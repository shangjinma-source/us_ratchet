"""Pure 127-session candidate/control argument assembly. Never runs an engine."""
import copy
import math
from datetime import date
import pandas as pd

CONTRACT=dict(initial_cash_usd=25000,minimum_cash_buffer_usd=100,transaction_cost_bps=10,
    max_single_weight=.45,min_single_weight=.05,top_weight_cap=.8,minimum_effective_n_ratio=.7,risk_chain_top1_cap=.55)
ORIGINAL_EIGHT={'NVDA','TXN','ASML','CDNS','TSM','MU','MSFT','GOOG'}


def number(value):
    if type(value) not in (float,int) or not math.isfinite(value):raise ValueError('Finite nonboolean numeric value required')
    return value


def canonical(value):
    if type(value) is not str or not value or value!=value.strip():raise ValueError('Canonical identity label required')
    return value


def typed_price(frame,calendar,tickers):
    if set(frame)!={'type','index_kind','index','columns','dtypes','data'} or frame['type']!='dataframe' or frame['index_kind']!='DatetimeIndex' or frame['index']!=[d+'T00:00:00' for d in calendar] or frame['columns']!=sorted(tickers) or frame['dtypes']!=['float64']*20 or len(frame['data'])!=253:raise ValueError('Complete source 253x20 nominal price matrix required')
    if any(len(row)!=20 or any(type(v) is not float or number(v)<=0 for v in row) for row in frame['data']):raise ValueError('Positive float64 Open/Close required')
    return pd.DataFrame(frame['data'][126:],columns=frame['columns'],index=pd.DatetimeIndex(calendar[126:]),dtype='float64')


def track(schedule,labels,risks,opens,closes,calendar,control):
    columns={sid:'SID_'+canonical(sid).upper().replace(':','_') for sid in labels}
    if len(set(columns.values()))!=len(columns):raise ValueError('Stable internal SID column collision')
    translated=copy.deepcopy(schedule)
    for row in translated:
        for sid,target in row['targets'].items():target['ticker']=columns[sid]
    frames={}
    for kind,frame in (('opens',opens),('closes',closes)):
        frames[kind]=pd.DataFrame({columns[sid]:frame[labels[sid]['ticker']].tolist() for sid in sorted(labels)},index=frame.index,dtype='float64')
    arguments=dict(**frames,schedule=translated,risk_chains_by_decision=copy.deepcopy(risks),corporate_actions=[],valuation_end_date=calendar[-1],**CONTRACT)
    if not control:arguments.update(identity_events=[],max_repair_evaluations=262144)
    marks={d:{sid:dict(ticker=r['ticker'],open=float(opens.loc[d,r['ticker']]),close=float(closes.loc[d,r['ticker']])) for sid,r in labels.items()} for d in calendar}
    return dict(arguments=arguments,original_schedule=copy.deepcopy(schedule),columns=columns,labels=copy.deepcopy(labels),prices=marks,
        restore_actual_ticker_by_security={sid:r['ticker'] for sid,r in labels.items()},risk_is_order_gate=not control,
        original_weights_normalized_by_assembler=False)


def assemble_account_arguments(*,inputs,schedule,risk_chains_by_decision):
    if inputs['schema']!='SOURCE_BOUND_TWENTY_CONDITIONAL_HISTORICAL_INPUTS_V1' or any(inputs[k] is not False for k in ('fit_performed','execution_performed','point_in_time_verified','legal_training_input_admitted','promotion_allowed','latest_weights_backfilled')):raise ValueError('Conditional historical input scope required')
    prices=inputs['prices'];calendar=prices['calendar']
    if len(calendar)!=253 or calendar!=sorted(set(calendar)) or any(date.fromisoformat(d).isoformat()!=d for d in calendar) or calendar[126]!='2026-03-18' or calendar[127]!='2026-03-19' or calendar[-1]!='2026-09-17':raise ValueError('Exact 253 source/127 execution clock required')
    window=calendar[126:]
    if prices['cash_dividends_included'] is not False or prices['known_evaluation_split_events']!=[] or prices['return_basis']!='SPLIT_ONLY_PRICE_RETURN_EXCLUDES_CASH_DIVIDENDS':raise ValueError('No dividend or action-aware execution authorization')
    for events in prices['submitted_full_split_events'].values():
        for event in events:
            if window[0]<event['session']<=window[-1]:raise ValueError('Known execution-window split requires action-aware engine')
    candidate_rows=inputs['candidate_coordinate_and_risk_rows'];control_rows=inputs['incumbent_original_securities']
    candidate={r['security_id']:r for r in candidate_rows};control={r['security_id']:r for r in control_rows}
    if len(candidate_rows)!=14 or len(candidate)!=14 or len({r['issuer_id'] for r in candidate_rows})!=14 or len({r['ticker'] for r in candidate_rows})!=14 or len(control_rows)!=8 or len(control)!=8 or len({r['issuer_id'] for r in control_rows})!=8 or {r['ticker'] for r in control_rows}!=ORIGINAL_EIGHT:raise ValueError('Original 14 candidate and fixed eight control coordinates required')
    for row in control_rows:
        if set(row)!={'security_id','issuer_id','ticker','risk_chain','target_weight'} or number(row['target_weight'])<=0:raise ValueError('Complete original five-field control definitions required')
        overlapping=[r for r in candidate_rows if r['ticker']==row['ticker']]
        if overlapping and any(overlapping[0][k]!=row[k] for k in ('security_id','issuer_id','risk_chain')):raise ValueError('Shared price channel has conflicting candidate/control coordinate')
    if not math.isclose(sum(r['target_weight'] for r in control_rows),1.,abs_tol=1e-12,rel_tol=0):raise ValueError('Original control weights must already sum to one')
    tickers={r['ticker'] for r in candidate_rows+control_rows}
    if len(tickers)!=20 or set(prices['submitted_full_split_events'])!=tickers:raise ValueError('Full twenty-channel price/event union required')
    lrcx,=[r for r in candidate_rows if r['ticker']=='LRCX']
    if lrcx['cusip']!='512807306' or not lrcx['security_id'].endswith(':512807306') or window[0]<'2024-10-03':raise ValueError('Post-transition LRCX coordinate only')
    opens=typed_price(prices['nominal_open'],calendar,tickers);closes=typed_price(prices['nominal_close'],calendar,tickers)
    if type(schedule) is not list or len(schedule)!=1 or set(schedule[0])!={'decision_date','execution_date','targets'}:raise ValueError('Exactly one explicit historical decision required')
    decision=schedule[0]
    if decision['decision_date']!=window[0] or decision['execution_date']!=window[1]:raise ValueError('Historical Close then next observed Open required')
    targets=decision['targets']
    if type(targets) is not dict or not targets or not set(targets)<=set(candidate):raise ValueError('Dynamic k must select a nonempty subset of fourteen')
    for sid,target in targets.items():
        source=candidate[sid]
        if set(target)!={'ticker','issuer_id','target_weight'} or any(target[k]!=source[k] for k in ('ticker','issuer_id')) or number(target['target_weight'])<=0:raise ValueError('Target contradicts source SID/issuer/ticker or positive weight')
    if not math.isclose(sum(t['target_weight'] for t in targets.values()),1.,abs_tol=1e-12,rel_tol=0):raise ValueError('Explicit target simplex required; assembler never normalizes')
    expected_risks={window[0]:{sid:candidate[sid]['risk_chain'] for sid in targets}}
    if risk_chains_by_decision!=expected_risks:raise ValueError('Target risk labels contradict source assumptions')
    for row in candidate_rows+control_rows:
        for key in ('security_id','issuer_id','ticker','risk_chain'):canonical(row[key])
    fixed_targets={sid:{k:row[k] for k in ('ticker','issuer_id','target_weight')} for sid,row in control.items()}
    fixed_schedule=[dict(decision_date=window[0],execution_date=window[1],targets=fixed_targets)]
    fixed_risks={window[0]:{sid:row['risk_chain'] for sid,row in control.items()}}
    return dict(schema='CONDITIONAL_SINGLE_WINDOW_ACCOUNT_ARGUMENTS_V1',calendar=window,contract=copy.deepcopy(CONTRACT),
        candidate=track(schedule,{s:candidate[s] for s in targets},expected_risks,opens,closes,window,False),
        incumbent=track(fixed_schedule,control,fixed_risks,opens,closes,window,True),
        supplied_historical_schedule_independently_authenticated=False,source_bytes_authenticated=False,security_identity_verified=False,
        historical_risk_assumptions_verified=False,point_in_time_verified=False,execution_performed=False,fit_performed=False,promotion_allowed=False)
