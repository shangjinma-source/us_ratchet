"""Register three continuous books, then explicitly run each once; no search."""
import argparse
from copy import deepcopy
from datetime import date
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
INPUT='tmp/fixed12_monthly_limit_inputs_20261014_v2/prepared.json'
INPUT_SHA='394e78f5eb7f0a5ff14ea7abb533bad7667726fdc6683f0a28e07751456657c8'
OUTPUT=ROOT/'tmp/fixed12_monthly_limit_execution_20261014_v1'
PINS={'backtest/return_priority_monthly_target_provider.py':'51876cae6bb4e1d19b1d8485113cae1bd1eca24815803a8b3f3a2ab264d7d14b',
      'backtest/return_priority_limit_book.py':'aca38fc156472a1a1e5c30fd509a58a89d8e7e674de4a95714a47a5191cb148a'}
PROTECTED=['data/state.json','data/broker_positions.json','config/config.yaml','api/server.py','web/index.html',
           'web/selected_stock_charts.js','data/current_cash_portfolio_research.py','data/current_quantity_portfolio_research.py']


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path,value):
    raw=json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False).encode('utf-8')
    with Path(path).open('xb') as f:f.write(raw)
    return hashlib.sha256(raw).hexdigest()


def guards():return {name:digest(ROOT/name) for name in PROTECTED}


def summarize(outcome,audit,initial_cash,session_dates):
    """Exact accounting totals; annualization is a labelled float diagnostic."""
    initial=Fraction(initial_cash);ledger=outcome.get('daily_ledger',[])
    equity=[initial]+[Fraction(r['equity']) for r in ledger]
    complete=outcome['status']=='COMPLETE' and bool(ledger) and ledger[-1]['date']==session_dates[-1]
    peak=initial;drawdown=Fraction(0)
    for v in equity:
        peak=max(peak,v);drawdown=max(drawdown,1-v/peak)
    elapsed=(date.fromisoformat(session_dates[-1])-date.fromisoformat(session_dates[0])).days
    logs=outcome.get('order_log',[])
    fills=[r for r in logs if r.get('event')=='ASSUMED_FILLED']
    expired=[r for r in logs if r.get('event')=='EXPIRED_UNFILLED']
    buys=sum((int(r['quantity'])*Fraction(r['price']) for r in fills if r['side']=='BUY'),Fraction(0))
    sells=sum((int(r['quantity'])*Fraction(r['price']) for r in fills if r['side']=='SELL'),Fraction(0))
    average=sum(equity)/len(equity)
    last_ready=next((r['response'] for r in reversed(audit) if r['response'].get('status')=='READY'),None)
    target=last_ready['target_shares'] if last_ready else {}
    actual=outcome.get('shares',{})
    differences={sid:target.get(sid,0)-actual.get(sid,0) for sid in sorted(set(target)|set(actual)) if target.get(sid,0)!=actual.get(sid,0)}
    ratio=equity[-1]/initial
    return dict(status=outcome['status'],complete_full_period=complete,
        total_return=str(ratio-1) if complete else None,
        annualized_return=(float(ratio)**(365/elapsed)-1) if complete and ratio>0 else None,
        annualization_basis=dict(calendar_days=elapsed,year_days=365,formula='(terminal_equity/initial_cash) ** (365/calendar_days) - 1',
            scope='Single continuous retrospective research account; not expected future performance.'),
        daily_close_maximum_drawdown=str(drawdown) if complete else None,partial_observed_drawdown=str(drawdown),
        terminal_equity=str(equity[-1]) if complete else None,last_observed_equity=str(equity[-1]),
        terminal_cash=outcome.get('cash'),terminal_positions=actual,terminal_receivable=outcome.get('receivable'),
        turnover=dict(buy_notional=str(buys),sell_notional=str(sells),gross_traded_notional=str(buys+sells),
            gross_notional_over_initial_equity=str((buys+sells)/initial),
            mean_observed_close_equity_including_initial=str(average),
            gross_notional_over_mean_observed_close_equity=str((buys+sells)/average) if average>0 else None,
            convention='Sum of buy and sell notionals; no half-turnover convention; no annualization.'),
        filled_orders=len(fills),expired_orders=len(expired),
        filled_order_fraction=str(Fraction(len(fills),len(fills)+len(expired))) if fills or expired else None,
        cash_wait_days=sum(bool(r['response'].get('wait_cash')) for r in audit),
        cash_wait_day_basis='Distinct causal close decisions with at least one remaining WAIT_CASH deficit.',
        target_reset_count=sum(r['response'].get('investable_equity_at_reset') is not None for r in audit),
        terminal_target=target,terminal_target_difference=differences,unfinished_rebalance=bool(differences),
        terminal_target_basis='Latest successful provider target; registered dataset has no terminal-session corporate actions.',
        provider_callbacks=len(audit),valued_sessions=len(ledger),blocked_reason=outcome.get('reason'),
        metrics_scope='FULL_CONTINUOUS_PERIOD' if complete else 'PARTIAL_BLOCKED_NOT_COMPLETED_PERIOD')


def validate(payload):
    calendar=payload['session_dates'];contract=payload['contract']
    if calendar!=sorted(set(calendar)) or calendar[0]!='2024-07-31' or calendar[-1]!='2025-07-30' or len(calendar)!=250:raise ValueError('Registered calendar differs')
    if [m['mode'] for m in payload['modes']]!=contract['modes'] or len(payload['modes'])!=3:raise ValueError('Exactly three frozen modes required')
    for m in payload['modes']:
        if m['status']!='READY_CONDITIONAL' or m['price_gaps']:raise ValueError('Unresolved source gap; no substitution')
        if m['initial_cash']!='20000' or m['initial_shares'] or Fraction(m['fee_bps']):raise ValueError('Initial cash/fee protocol differs')
        if [d['decision_date'] for d in m['monthly_decisions']]!=contract['decision_dates']:raise ValueError('Frozen monthly schedule differs')
        if m['actions']:raise ValueError('This registration only covers the audited zero-exposed-action dataset; no generic migration claim')
    for name,h in payload['source_hashes'].items():
        if digest(ROOT/name)!=h:raise ValueError('Input closure changed: '+name)


def prepare():
    if OUTPUT.exists():raise ValueError('Create-only output already exists')
    if digest(ROOT/INPUT)!=INPUT_SHA:raise ValueError('Reviewed continuous dataset differs')
    payload=json.loads((ROOT/INPUT).read_bytes());validate(payload)
    pins=dict(payload['source_hashes']);pins[INPUT]=INPUT_SHA
    for name,h in PINS.items():
        if digest(ROOT/name)!=h:raise ValueError('Reviewed provider/kernel differs')
        pins[name]=h
    for name in ('tmp/fixed12_monthly_provider_author_checks_20261014_v1.json',
                 'tmp/fixed12_monthly_inputs_independent_readback_20261014_v1.json',str(Path(__file__).resolve())):
        pins[name]=digest(ROOT/name)
    registration=dict(input_path=INPUT,input_sha256=INPUT_SHA,runner_sha256=digest(__file__),source_hashes=pins,
        protected_before=guards(),maximum_book_calls=3,maximum_search_calls=0,initial_cash_each='20000',
        monthly_cash_reset=False,modes=[m['mode'] for m in payload['modes']],automatic_retry_allowed=False,
        denominator=3,independent_oos=False,adoption_allowed=False,execution_assumption=payload['contract']['execution_assumption'])
    OUTPUT.mkdir();print(save(OUTPUT/'registration.json',registration))


def run(registration_sha):
    if digest(OUTPUT/'registration.json')!=registration_sha:raise ValueError('Reviewed registration differs')
    if {p.name for p in OUTPUT.iterdir()}!={'registration.json'}:raise ValueError('Already started; inspect artifacts, never retry')
    reg=json.loads((OUTPUT/'registration.json').read_bytes())
    if digest(__file__)!=reg['runner_sha256']:raise ValueError('Runner differs')
    for name,h in reg['source_hashes'].items():
        if digest(ROOT/name)!=h:raise ValueError('Pinned source differs: '+name)
    if guards()!=reg['protected_before']:raise ValueError('Protected state changed')
    payload=json.loads((ROOT/INPUT).read_bytes());validate(payload)
    from backtest.return_priority_monthly_target_provider import build_monthly_target_provider
    from backtest.return_priority_limit_book import run_limit_book
    save(OUTPUT/'started.json',dict(registration_sha256=registration_sha,maximum_book_calls=3,search_calls=0))
    results=[]
    try:
        for mode in payload['modes']:
            directory=OUTPUT/mode['mode'];directory.mkdir()
            save(directory/'intent.json',dict(maximum_calls=1,mode=mode['mode'],initial_cash='20000',initial_shares={},automatic_retry_allowed=False))
            audit=[]
            def recorded_provider(*,decision_date,active_date,state):
                response=provider(decision_date=decision_date,active_date=active_date,state=state)
                record=dict(decision_date=decision_date,active_date=active_date,prior_cash=state['cash'],prior_shares=deepcopy(state['shares']),
                    response=deepcopy(response))
                audit.append(record)
                return response
            try:
                provider=build_monthly_target_provider(session_dates=payload['session_dates'],monthly_decisions=mode['monthly_decisions'],
                    close_prices={sid:{d:r['close'] for d,r in rows.items()} for sid,rows in mode['ohlc'].items()},actions=mode['actions'])
                outcome=run_limit_book(session_dates=payload['session_dates'],ohlc=mode['ohlc'],initial_cash=mode['initial_cash'],
                    initial_shares=mode['initial_shares'],events=mode['actions'],fee_bps=mode['fee_bps'],order_provider=recorded_provider)
            except (ValueError,KeyError,TypeError,ZeroDivisionError) as error:
                outcome=dict(status='BLOCKED_EXCEPTION',reason=dict(type=type(error).__name__,detail=str(error)),daily_ledger=[],order_log=[],
                    cash=None,shares={},receivable=None,state_not_reconstructed_after_exception=True)
            save(directory/'provider_audit.json',audit);save(directory/'outcome.json',outcome)
            metrics=summarize(outcome,audit,mode['initial_cash'],payload['session_dates'])
            save(directory/'metrics.json',metrics);results.append(dict(mode=mode['mode'],**metrics))
        save(OUTPUT/'result.json',dict(modes=results,book_calls=len(results),search_calls=0,denominator=3,
            initial_cash_reset_only_between_independent_modes=True,monthly_reset=False,independent_oos=False,adoption_allowed=False))
    finally:
        after=guards();save(OUTPUT/'protected_after.json',dict(hashes=after,unchanged=after==reg['protected_before']))
        if after!=reg['protected_before']:raise ValueError('Protected state changed during execution')


if __name__=='__main__':
    p=argparse.ArgumentParser();g=p.add_mutually_exclusive_group(required=True);g.add_argument('--prepare',action='store_true');g.add_argument('--run',action='store_true');p.add_argument('--registration-sha');a=p.parse_args()
    if a.prepare:prepare()
    elif a.registration_sha:run(a.registration_sha)
    else:raise ValueError('Reviewed registration hash required')
