"""One bounded fixed ten-month trend experiment; production and baselines stay frozen."""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys
import time
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.run_old_continuous_probe_v1 import save, validate_selection_binding

def digest(path):return sha256(Path(path).read_bytes()).hexdigest()

def check_pins(pins):
    for name,expected in pins.items():
        if digest(ROOT/name)!=expected:raise ValueError('SOURCE_CHANGED:'+name)

def checkpoint_selection(*, arguments, signal, binding, output, reuse, select, budget):
    """Only identical branch, account, signal and evidence can reuse a search."""
    day=arguments['decision_date']
    prior=Path(reuse)/f'{day}.selection.json' if reuse else None
    expected=dict(arguments=arguments,signal=signal,experiment_binding=binding)
    if prior and prior.exists():
        checkpoint=json.loads(prior.read_text())
        if any(checkpoint.get(key)!=value for key,value in expected.items()):
            raise ValueError('EXACT_BRANCH_CHECKPOINT_REQUIRED:'+day)
        raw=checkpoint['raw_selection'];budget['reused']+=1
    else:
        if budget['new']>=budget['maximum']:raise ValueError('NEW_SEARCH_LIMIT_REACHED')
        raw=select(**arguments);budget['new']+=1
    save(Path(output)/f'{day}.selection.json',dict(expected,raw_selection=raw))
    validate_selection_binding(raw,arguments)
    return raw


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('baseline-inputs','baseline-book','signals','prices','action-review','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--reuse',type=Path)
    parser.add_argument('--seconds',type=int,required=True)
    parser.add_argument('--run',action='store_true')
    parser.add_argument('--worker',action='store_true',help=argparse.SUPPRESS)
    parser.add_argument('--launch-pins',help=argparse.SUPPRESS)
    options=parser.parse_args()
    if not 0<options.seconds<=3600:raise ValueError('EXPLICIT_1_TO_3600_SECONDS_REQUIRED')
    files={name:str(getattr(options,name).resolve()) for name in ('baseline_inputs','baseline_book','signals','prices','action_review')}
    pins={name:digest(path) for name,path in files.items()}
    pins['trend_module']=digest(ROOT/'backtest/long_market_trend_research_v1.py')
    if options.worker and (not options.launch_pins or json.loads(options.launch_pins)!=pins):
        raise ValueError('BOUNDED_PARENT_EXACT_INPUT_PINS_REQUIRED')
    document=json.loads(options.baseline_inputs.read_text())
    baseline=json.loads(options.baseline_book.read_text())
    if baseline['status']!='COMPLETE':raise ValueError('COMPLETE_BASELINE_REQUIRED')
    assembled=document['assembled'];months=len(assembled['monthly_inputs'])
    if months not in (31,36):raise ValueError('FIXED_TWO_WINDOWS_ONLY')
    expected_interval=('2020-12-31','2023-12-29') if months==36 else ('2023-12-29','2026-07-30')
    if (assembled['session_dates'][0],assembled['session_dates'][-1])!=expected_interval:
        raise ValueError('FROZEN_BASELINE_INTERVAL_REQUIRED')
    check_pins(assembled['source_hashes']);check_pins(document.get('action_source_hashes',{}))
    signal_document=json.loads(options.signals.read_text());check_pins(signal_document['source_hashes'])
    review=json.loads(options.action_review.read_text());check_pins(review['source_hashes'])
    if digest(options.action_review)!=document['action_review_sha256']:
        raise ValueError('BASELINE_ACTION_REVIEW_BINDING_REQUIRED')
    for plan in assembled['monthly_inputs']:
        args=plan['search_arguments']
        if (args['max_objective_evaluations']!=8192 or str(args['fee_bps'])!='0'
                or str(args['minimum_cash_buffer'])!='0' or args['fixed_seed']!='fresh-quantity-20261014-v1'):
            raise ValueError('FROZEN_SELECTION_BUDGET_REQUIRED')
    window_name='2021_2023' if months==36 else '2024_2026'
    matches=[w for w in signal_document['windows'] if w['name']==window_name]
    if len(matches)!=1:raise ValueError('EXACT_SIGNAL_WINDOW_REQUIRED')
    signals={row['decision_date']:row for row in matches[0]['inputs']}
    if set(signals)!={p['decision_date'] for p in assembled['monthly_inputs']}:raise ValueError('SIGNAL_DATES_MISMATCH')
    from backtest.long_market_trend_research_v1 import signal_proof
    for record in signals.values():
        signal_proof(record)
        if any(row['source'] not in signal_document['source_hashes'] for row in record['completed_month_end_prices']):
            raise ValueError('UNPINNED_SIGNAL_SOURCE')
    expected_price_hash=document.get('execution_prices_sha256') or ('3a0c0d3cc2b917a34c6f4328876dda50ee4cd8509af5c08e10fd86218729dfbf' if months==31 else None)
    if not expected_price_hash or digest(options.prices)!=expected_price_hash:
        raise ValueError('BASELINE_PRICE_HASH_MISMATCH')
    if not options.worker:
        if not options.run:
            print(json.dumps(dict(status='PREFLIGHT_ONLY',months=months,max_searches=months,seconds=options.seconds)))
            return
        from backtest.bounded_research_process import run_worker
        arguments=['--worker','--seconds',str(options.seconds),'--output',str(options.output.resolve()),'--launch-pins',json.dumps(pins)]
        for name,path in files.items():arguments+=['--'+name.replace('_','-'),path]
        if options.reuse:arguments+=['--reuse',str(options.reuse.resolve())]
        print(json.dumps(run_worker(script=__file__,expected_sha256=digest(__file__),arguments=arguments,output_directory=options.output,timeout_seconds=options.seconds)))
        return
    from backtest.long_market_trend_research_v1 import run_trend,signal_proof
    from backtest.continuous_guided_account_decision import decide_continuous_guided_for_account
    from backtest.monthly_exit_core_research_adapter import MonthlyExitCoreResearchAdapter
    if not options.output.is_dir():raise ValueError('BOUNDED_PARENT_REQUIRED')
    with (options.output/'attempt.lock').open('x') as stream:stream.write('One bounded attempt, no retries.')
    binding=dict(input_hashes={key:value for key,value in pins.items() if key!='action_review'},runner_sha256=digest(__file__),trend_module_sha256=digest(ROOT/'backtest/long_market_trend_research_v1.py'))
    budget=dict(new=0,reused=0,maximum=months)
    prices=json.loads(options.prices.read_text())
    started=time.monotonic()
    def selector(**arguments):
        if time.monotonic()-started>=options.seconds:raise ValueError('TIME_BUDGET_REACHED')
        return checkpoint_selection(arguments=arguments,signal=signal_proof(signals[arguments['decision_date']]),
            binding=binding,output=options.output,reuse=options.reuse,select=decide_continuous_guided_for_account,budget=budget)
    dates=[plan['decision_date'] for plan in assembled['monthly_inputs']]+[assembled['session_dates'][-1]]
    def decision_callback(arguments,selected):
        day=arguments['decision_date'];end=dates[dates.index(day)+1]
        active=assembled['session_dates'][assembled['session_dates'].index(day)+1]
        save(options.output/f'{day}.decision.json',dict(arguments=arguments,selected=selected,experiment_binding=binding))
        if months==36:
            from scripts.run_recent_continuous_probe import exposed_action_blockers
            gate=exposed_action_blockers(arguments,selected,end,prices,review,active,document['dividend_events'])
        else:
            from scripts.assemble_old_continuous_inputs_v1 import exposure_gate
            from scripts.run_old_continuous_probe_v4 import admit_reviewed_dividends,admit_period_absence,admit_split_liquidation
            gate=exposure_gate(document,arguments,selected,end,active)
            gate=admit_reviewed_dividends(gate,review,document['dividend_events'])
            gate=admit_period_absence(gate,review)
            gate=admit_split_liquidation(gate,arguments,selected,assembled['actions'],active)
        save(options.output/f'{day}.exposure.json',gate)
        if not gate['admitted']:raise ValueError('TREND_BRANCH_EXPOSURE_NOT_ADMITTED:'+day)
    save(options.output/'execution_inputs.json',dict(baseline_execution_inputs=document,signals=signals,
        experiment_binding=binding,execution_input_hashes=pins,action_review=review,signal_source_hashes=signal_document['source_hashes']))
    book=run_trend(signals=signals,signal_source_hashes=signal_document['source_hashes'],assembled=assembled,
        ohlc=document['ohlc'],initial_cash='20000',fee_bps='0',slippage_bps='5',
        risk=MonthlyExitCoreResearchAdapter(assembled['actions']),max_new_searches=months,
        dividend_events=document['dividend_events'],selector=selector,decision_callback=decision_callback)
    book.update(actual_new_searches=budget['new'],actual_reused_searches=budget['reused'])
    save(options.output/'book.json',book)
    save(options.output/'summary.json',dict(status=book['status'],reason=book.get('reason'),
        completed_sessions=len(book['daily_ledger']),searches=budget,performance_validated=False))
    print(json.dumps(dict(status=book['status'],searches=budget)))

if __name__=='__main__':main()
