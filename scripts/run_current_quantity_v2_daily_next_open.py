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
from backtest.current_quantity_v2_daily_next_open import run_daily_next_open
from backtest.continuous_calendar_year_metrics import calendar_year_metrics
from data.current_research_capital_decision_v2 import REQUIRED_PINS


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--prepared',required=True)
    parser.add_argument('--output',required=True)
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
            'backtest/continuous_calendar_year_metrics.py',
            'scripts/run_current_quantity_v2_daily_next_open.py'}
        for name in code:pins[name]=hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
        prepared['source_hashes']=pins
        assembled=assemble_monthly_execution_inputs_v4(prepared)
        receipt=dict(status='PREFLIGHT_PASSED_NOT_EXECUTED',prepared_sha256=hashlib.sha256(raw).hexdigest(),
            source_hashes=pins,initial_cash=args.initial_cash,fee_bps=args.fee_bps,slippage_bps=args.slippage_bps,
            sessions=[assembled['session_dates'][0],assembled['session_dates'][-1]],
            policy='DAILY_CLOSE_SIGNAL_NEXT_OPEN_EXECUTION_NOT_PULLBACK',
            ordinary_cash_dividends_included=False,unmodeled_charges_unknown=True,
            point_in_time_certified=False,independent_oos=False)
        write('preflight.json',receipt)
        if not args.execute:
            write('terminal.json',dict(status='PREFLIGHT_ONLY',finished_at=stamp(),search_calls=0))
            return
        def progress(row):
            with (out/'progress.jsonl').open('a',encoding='utf-8') as stream:
                stream.write(json.dumps(dict(row,observed_at=stamp()))+'\n')
        result=run_daily_next_open(assembled=assembled,ohlc=prepared['ohlc'],initial_cash=args.initial_cash,
            fee_bps=args.fee_bps,slippage_bps=args.slippage_bps,progress=progress)
        write('outcome.json',result)
        changed=[name for name,digest in pins.items() if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest]
        if changed:raise ValueError('SOURCE_CHANGED_DURING_RUN:'+str(changed))
        metric=dict(status=result['status'],reason=result['reason'],total_return=result['total_return'],
                    drawdown=result['drawdown'],annualized_return=None,calendar_year_returns_not_computed=True)
        if result['status']=='COMPLETE':
            yearly=calendar_year_metrics(
                opening_date=assembled['session_dates'][0],opening_equity=args.initial_cash,
                daily_ledger=result['daily_ledger'],expected_sessions=assembled['session_dates'][1:],
                report_through=assembled['session_dates'][-1])
            elapsed=(date.fromisoformat(assembled['session_dates'][-1])-date.fromisoformat(assembled['session_dates'][0])).days
            from fractions import Fraction
            metric['annualized_return']=float(1+Fraction(result['total_return']))**(365/elapsed)-1
            metric['calendar_year_returns_not_computed']=False
            metric['calendar_year_metrics']=yearly
            write('calendar_year_metrics.json',yearly)
        write('metrics.json',metric)
        write('terminal.json',dict(status=result['status'],finished_at=stamp(),source_pins_unchanged=True))
    except Exception as error:
        write('terminal.json',dict(status='ERROR',finished_at=stamp(),error=type(error).__name__+':'+str(error)))
        raise


if __name__=='__main__':main()
