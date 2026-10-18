"""Explicit offline experiment runner; default preflight, --execute opt-in."""
import argparse
import hashlib
import json
from datetime import datetime, timezone, date
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backtest.return_priority_monthly_execution_inputs_v4 import assemble_monthly_execution_inputs_v4
from backtest.current_quantity_v2_simple253_next_open import run_simple253_next_open
from backtest.current_quantity_v2_simple253 import validate_training, compare_saved_v2_states
from data.current_research_capital_decision_v2 import REQUIRED_PINS


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--prepared',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--training',required=True)
    parser.add_argument('--v2-outcome',required=True)
    parser.add_argument('--initial-cash',required=True)
    parser.add_argument('--fee-bps',required=True)
    parser.add_argument('--slippage-bps',required=True)
    parser.add_argument('--execute',action='store_true')
    args=parser.parse_args()
    source=(ROOT/args.prepared).resolve()
    out=(ROOT/args.output).resolve()
    if not out.is_relative_to(ROOT/'tmp'):raise ValueError('OUTPUT_MUST_BE_NEW_TMP_DIRECTORY')
    out.mkdir(exist_ok=False)
    def write(name,value):
        (out/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    def stamp():return datetime.now(timezone.utc).isoformat()
    write('started.json',dict(started_at=stamp(),execute=args.execute,arguments=vars(args)))
    try:
        raw=source.read_bytes();prepared=json.loads(raw)
        pins=dict(prepared['source_hashes'])
        for name,digest in pins.items():
            if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest:
                raise ValueError('SOURCE_DRIFT:'+name)
        code=set(REQUIRED_PINS)|{
            'backtest/current_quantity_v2_daily_next_open.py','backtest/current_quantity_v2_next_open_book.py',
            'scripts/run_current_quantity_v2_simple253.py','backtest/current_quantity_v2_simple253.py',
            'backtest/current_quantity_v2_simple253_next_open.py'}
        for name in code:pins[name]=hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
        prepared['source_hashes']=pins
        assembled=assemble_monthly_execution_inputs_v4(prepared)
        training_path=(ROOT/args.training).resolve()
        training_raw=training_path.read_bytes();training=json.loads(training_raw)
        training_key=training_path.relative_to(ROOT).as_posix()
        if pins.get(training_key)!=hashlib.sha256(training_raw).hexdigest():raise ValueError('TRAINING_ARCHIVE_NOT_BOUND_BY_PREPARED')
        for name,digest in training['source_hashes'].items():
            if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest:raise ValueError('TRAINING_SOURCE_DRIFT:'+name)
            if name in pins and pins[name]!=digest:raise ValueError('TRAINING_PIN_CONFLICT:'+name)
            pins[name]=digest
        training_windows=training['windows']
        training_by_date={w['decision_cutoff']:w for w in training_windows}
        calendar=sorted({day for w in training_windows for day in w['training_dates']})
        if set(training_by_date)!={w['decision_date'] for w in assembled['monthly_inputs']}:raise ValueError('TRAINING_MONTH_DOMAIN_MISMATCH')
        for w in assembled['monthly_inputs']:
            validate_training(window=training_by_date[w['decision_date']],arguments=w['search_arguments'],calendar=calendar)
        pins[str(training_path.relative_to(ROOT))]=hashlib.sha256(training_raw).hexdigest()
        v2_path=(ROOT/args.v2_outcome).resolve();v2_raw=v2_path.read_bytes();v2=json.loads(v2_raw)
        if v2['status']!='COMPLETE':raise ValueError('COMPLETE_V2_REFERENCE_REQUIRED')
        terminal_path=v2_path.parent/'terminal.json';terminal_raw=terminal_path.read_bytes();terminal=json.loads(terminal_raw)
        if terminal.get('status')!='COMPLETE' or terminal.get('source_pins_unchanged') is not True:raise ValueError('BASELINE_TERMINAL_NOT_VERIFIED')
        pins[terminal_path.relative_to(ROOT).as_posix()]=hashlib.sha256(terminal_raw).hexdigest()
        prior_path=v2_path.parent/'preflight.json';prior_raw=prior_path.read_bytes();prior=json.loads(prior_raw)
        from fractions import Fraction
        if prior.get('policy')!='DAILY_CLOSE_SIGNAL_NEXT_OPEN_EXECUTION_NOT_PULLBACK':raise ValueError('DIFFERENT_BASELINE_POLICY')
        if prior['prepared_sha256']!=hashlib.sha256(raw).hexdigest():raise ValueError('DIFFERENT_PREPARED_BASELINE')
        for key in ('initial_cash','fee_bps','slippage_bps'):
            if Fraction(str(prior[key]))!=Fraction(str(getattr(args,key))):raise ValueError('DIFFERENT_BASELINE_'+key)
        if [row['date'] for row in v2['daily_ledger']]!=assembled['session_dates'][1:]:raise ValueError('DIFFERENT_BASELINE_CALENDAR')
        for name,digest in prior['source_hashes'].items():
            if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest:raise ValueError('BASELINE_SOURCE_DRIFT:'+name)
        pins[prior_path.relative_to(ROOT).as_posix()]=hashlib.sha256(prior_raw).hexdigest()
        pins[str(v2_path.relative_to(ROOT))]=hashlib.sha256(v2_raw).hexdigest()
        comparison=compare_saved_v2_states(outcome=v2,training_windows=training_windows)
        if [row['decision_date'] for row in comparison]!=[w['decision_date'] for w in assembled['monthly_inputs']]:raise ValueError('COMPARISON_MONTHS_MISSING_DUPLICATE_OR_UNORDERED')
        write('same_state_comparison.json',comparison)
        receipt=dict(status='PREFLIGHT_PASSED_NOT_EXECUTED',prepared_sha256=hashlib.sha256(raw).hexdigest(),
            source_hashes=pins,initial_cash=args.initial_cash,fee_bps=args.fee_bps,slippage_bps=args.slippage_bps,
            sessions=[assembled['session_dates'][0],assembled['session_dates'][-1]],
            policy='DAILY_CLOSE_SIGNAL_NEXT_OPEN_EXECUTION_NOT_PULLBACK',
            ordinary_cash_dividends_included=False,unmodeled_charges_unknown=True,
            point_in_time_certified=False,independent_oos=False,
            newly_known_source_gap=dict(ticker='TRI',effective_date='2026-05-04',capital_return_usd='1.435518',consolidation_ratio='0.984560',old_cusip='884903808',new_cusip='884903881',status='ROOT_REPORTED_OFFICIAL_EVIDENCE_PENDING_TRAINING_IDENTITY_IMPACT_REVIEW',scope='Frozen input omitted action; mechanism checks are old-coordinate conditional counterfactuals, not certified real-return comparisons.'),
            economic_execution_gate='BLOCKED_PENDING_TRI_IMPACT_REVIEW')
        if any(hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest for name,digest in pins.items()):raise ValueError('SOURCE_CHANGED_DURING_PREFLIGHT')
        write('preflight.json',receipt)
        if not args.execute:
            write('terminal.json',dict(status='PREFLIGHT_ONLY',finished_at=stamp(),search_calls=0,baseline_same_state_calls=len(comparison)))
            return
        raise ValueError('ECONOMIC_EXECUTION_BLOCKED_PENDING_TRI_IMPACT_REVIEW')
        def progress(row):
            with (out/'progress.jsonl').open('a',encoding='utf-8') as stream:
                stream.write(json.dumps(dict(row,observed_at=stamp()))+'\n')
        result=run_simple253_next_open(assembled=assembled,training_windows=training_windows,ohlc=prepared['ohlc'],initial_cash=args.initial_cash,
            fee_bps=args.fee_bps,slippage_bps=args.slippage_bps,progress=progress)
        write('outcome.json',result)
        changed=[name for name,digest in pins.items() if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest]
        if changed:raise ValueError('SOURCE_CHANGED_DURING_RUN:'+str(changed))
        metric=dict(status=result['status'],reason=result['reason'],total_return=result['total_return'],
                    drawdown=result['drawdown'],annualized_return=None,calendar_year_returns_not_computed=True)
        if result['status']=='COMPLETE':
            elapsed=(date.fromisoformat(assembled['session_dates'][-1])-date.fromisoformat(assembled['session_dates'][0])).days
            from fractions import Fraction
            metric['annualized_return']=float(1+Fraction(result['total_return']))**(365/elapsed)-1
        write('metrics.json',metric)
        write('terminal.json',dict(status=result['status'],finished_at=stamp(),source_pins_unchanged=True))
    except Exception as error:
        write('terminal.json',dict(status='ERROR',finished_at=stamp(),error=type(error).__name__+':'+str(error)))
        raise


if __name__=='__main__':main()
