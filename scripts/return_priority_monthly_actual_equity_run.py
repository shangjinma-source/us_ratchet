"""Single registered continuous actual-equity research book; explicit run only."""
import argparse
from copy import deepcopy
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from scripts.return_priority_fixed12_monthly_limit_run import summarize, guards
from backtest.return_priority_monthly_execution_inputs import assemble_monthly_execution_inputs
INPUT='tmp/current_monthly_actual_equity_inputs_20261014_v2/prepared.json'
INPUT_SHA='611fcca3b0dccb30314ded89d17c810a2f4aa52d899134afa8c6edeab1f5c6f8'
REUSE='tmp/monthly_initial_search_reuse_20261014_v1.json'
SAVED_INPUT='tmp/fixed12_quantity_search_20261014_v1/2024-07-31/inputs.json'
SAVED_RESULT='tmp/fixed12_quantity_search_20261014_v1/2024-07-31/search.json'
OUTPUT=ROOT/'tmp/monthly_actual_equity_execution_20261014_v1'
MODULES=['backtest/return_priority_limit_book_v3.py','backtest/return_priority_monthly_quantity_provider_v3.py',
 'backtest/return_priority_limit_book_v2.py','backtest/return_priority_cash_stock_entitlements.py',
 'backtest/return_priority_fresh_cash_quantity_search.py','backtest/return_priority_monthly_execution_inputs.py',
 'data/current_research_capital_decision.py','scripts/return_priority_fixed12_monthly_limit_run.py',
 'scripts/return_priority_monthly_actual_equity_run.py',
 'research_contracts/monthly_split_limit_rounding_20261014_v1.json',
 'research_contracts/monthly_actual_equity_validation_20261014_v1.json']


def digest(path):return hashlib.sha256((ROOT/path).read_bytes()).hexdigest()
def load(path):return json.loads((ROOT/path).read_bytes())
def plain(value):
    if isinstance(value,Fraction):return str(value)
    if isinstance(value,dict):return {k:plain(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [plain(v) for v in value]
    return value

def save(path,value):
    with path.open('x',encoding='utf-8') as stream:json.dump(plain(value),stream,ensure_ascii=False,indent=2,allow_nan=False)

def verify(pins):
    for path,expected in pins.items():
        if digest(path)!=expected:raise ValueError('PIN_CHANGED:'+path)

def validate(prepared):
    if digest(INPUT)!=INPUT_SHA:raise ValueError('DATASET_CHANGED')
    verify(prepared['source_hashes']);assembled=assemble_monthly_execution_inputs(prepared)
    calendar=assembled['session_dates'];windows=assembled['monthly_inputs']
    if len(calendar)!=250 or calendar[0]!='2024-07-31' or calendar[-1]!='2025-07-30' or len(windows)!=12:raise ValueError('CALENDAR_SCOPE_CHANGED')
    if len({w['active_date'][:7] for w in windows})!=12:raise ValueError('DUPLICATE_TARGET_MONTH')
    for w in windows:
        args=w['search_arguments']
        if args['max_objective_evaluations']!=8192 or args['fixed_seed']!='fresh-quantity-20261014-v1' or Fraction(args['fee_bps']) or Fraction(args['minimum_cash_buffer']):raise ValueError('SEARCH_PROTOCOL_CHANGED')
    return assembled

def prepare():
    if OUTPUT.exists():raise ValueError('CREATE_ONLY_OUTPUT_EXISTS')
    if digest('backtest/return_priority_limit_book_v3.py')!='7f1ac84aed43d96353d7dea9da445a1fa460a4b9797c1da4f78165a158015593' or digest('backtest/return_priority_monthly_quantity_provider_v3.py')!='273c61016b64e967fb8818a3db042a66c301d5aa2a013dc6df8010197bf0cceb':raise ValueError('REVIEWED_V3_CHANGED')
    prepared=load(INPUT);assembled=validate(prepared);reuse=load(REUSE);verify(reuse['source_hashes'])
    original=load(SAVED_INPUT)['search_arguments'];incoming=deepcopy(assembled['monthly_inputs'][0]['search_arguments']);incoming.pop('quote_as_of');incoming.pop('price_basis')
    if incoming!=original or load(SAVED_RESULT)['selected']!=reuse['selected']:raise ValueError('INITIAL_REUSE_MISMATCH')
    pins=dict(prepared['source_hashes']);pins.update(reuse['source_hashes'])
    for path in MODULES+[INPUT,REUSE]:pins[path]=digest(path)
    registration=dict(schema='MONTHLY_ACTUAL_EQUITY_EXECUTION_V1',source_hashes=pins,protected_before=guards(),
        input_path=INPUT,maximum_book_calls=1,maximum_new_search_calls=11,maximum_total_monthly_decisions=12,
        initial_search_reuse_only='2024-07-31',initial_cash='20000',monthly_cash_reset=False,automatic_retry_allowed=False,
        decision_dates=[w['decision_date'] for w in assembled['monthly_inputs']],denominator=1,
        independent_oos=False,adoption_allowed=False,price_only_excludes_cash_dividends=True,
        execution_assumption='OHLC touch assumes complete fill with open improvement; queue/liquidity unproven; conservative split-limit cent rounding is a research assumption.')
    OUTPUT.mkdir();save(OUTPUT/'registration.json',registration)
    print(digest(str(OUTPUT/'registration.json')))

def run(registration_sha):
    if digest(str(OUTPUT/'registration.json'))!=registration_sha:raise ValueError('REGISTRATION_CHANGED')
    if {p.name for p in OUTPUT.iterdir()}!={'registration.json'}:raise ValueError('ALREADY_STARTED_NO_RETRY')
    reg=load(str(OUTPUT/'registration.json'));verify(reg['source_hashes'])
    if guards()!=reg['protected_before']:raise ValueError('PROTECTED_STATE_CHANGED')
    prepared=load(INPUT);assembled=validate(prepared)
    from backtest.return_priority_fresh_cash_quantity_search import search_fresh_cash_quantities
    from data.current_research_capital_decision import decide_quantity_for_account
    from backtest.return_priority_monthly_quantity_provider_v3 import build_monthly_quantity_provider_v3
    from backtest.return_priority_limit_book_v3 import run_limit_book_v3
    save(OUTPUT/'started.json',dict(registration_sha256=registration_sha,maximum_book_calls=1,maximum_new_search_calls=11))
    audit=[];calls=[];current_state=None
    def search(**kwargs):
        day=kwargs['decision_date']
        if day not in reg['decision_dates'] or day in calls:raise ValueError('UNREGISTERED_OR_DUPLICATE_SEARCH')
        directory=OUTPUT/day;directory.mkdir()
        save(directory/'intent.json',dict(core_arguments=kwargs,prior_state=current_state,maximum_calls=0 if day==reg['initial_search_reuse_only'] else 1))
        calls.append(day)
        if day==reg['initial_search_reuse_only']:
            if kwargs!=load(SAVED_INPUT)['search_arguments']:raise ValueError('RUNTIME_INITIAL_REUSE_MISMATCH_NO_SEARCH_FALLBACK')
            result=load(SAVED_RESULT)
        else:
            if len([d for d in calls if d!=reg['initial_search_reuse_only']])>11:raise ValueError('SEARCH_BUDGET_EXCEEDED')
            result=search_fresh_cash_quantities(**kwargs)
        save(directory/'search.json',result)
        return result
    def decide(**kwargs):
        return decide_quantity_for_account(search=search,**kwargs)
    provider=build_monthly_quantity_provider_v3(session_dates=assembled['session_dates'],monthly_inputs=assembled['monthly_inputs'],
        close_prices=assembled['close_prices'],actions=assembled['provider_actions'],decide=decide)
    def callback(*,decision_date,active_date,state):
        nonlocal current_state
        current_state=deepcopy(state)
        record=dict(decision_date=decision_date,active_date=active_date,prior_state=current_state)
        try:
            response=provider(decision_date=decision_date,active_date=active_date,state=state)
        except Exception as error:
            response=dict(status='BLOCKED',reason=type(error).__name__+':'+str(error),orders=[])
        record['response']=deepcopy(response);audit.append(record)
        save(OUTPUT/('callback_'+decision_date+'.json'),record)
        return response
    try:
        try:
            outcome=run_limit_book_v3(session_dates=assembled['session_dates'],ohlc=prepared['ohlc'],initial_cash='20000',initial_shares={},
                events=assembled['actions'],fee_bps='0',order_provider=callback,cash_stock_merger_events=assembled['cash_stock_merger_events'],
                fractional_settlements=assembled['fractional_settlements'],price_source_references=assembled['price_source_references'])
        except Exception as error:
            save(OUTPUT/'exception.json',dict(type=type(error).__name__,message=str(error),partial_callback_files_preserved=True))
            outcome=dict(status='BLOCKED_EXCEPTION',reason=str(error),daily_ledger=[],order_log=[],cash=None,shares={},receivable=None)
        save(OUTPUT/'outcome.json',outcome);save(OUTPUT/'provider_audit.json',audit)
        metrics=summarize(outcome,audit,'20000',assembled['session_dates'])
        metrics.update(nontradable_rights=outcome.get('merger_entitlements'),rights_valuation=outcome.get('rights_valuation'),
            terminal_tradable_cash=outcome.get('cash'),equity_scope='PRICE_ONLY_TRADABLE_ASSETS_PLUS_CONDITIONAL_NONTRADABLE_RIGHTS; NOT_DIVIDEND_TOTAL_RETURN')
        save(OUTPUT/'result.json',dict(metrics=metrics,book_calls=1,new_search_calls=sum(d!=reg['initial_search_reuse_only'] for d in calls),
            initial_search_reused=reg['initial_search_reuse_only'] in calls,denominator=1,independent_oos=False,adoption_allowed=False))
    finally:
        after=guards();save(OUTPUT/'protected_after.json',dict(hashes=after,unchanged=after==reg['protected_before']))
        if after!=reg['protected_before']:raise ValueError('PROTECTED_STATE_CHANGED')

if __name__=='__main__':
    parser=argparse.ArgumentParser();group=parser.add_mutually_exclusive_group(required=True);group.add_argument('--prepare',action='store_true');group.add_argument('--run',action='store_true');parser.add_argument('--registration-sha');args=parser.parse_args()
    if args.prepare:prepare()
    elif args.registration_sha:run(args.registration_sha)
    else:raise ValueError('EXPLICIT_REVIEWED_REGISTRATION_SHA_REQUIRED')
