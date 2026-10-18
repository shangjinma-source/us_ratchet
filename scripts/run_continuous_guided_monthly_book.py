"""One isolated continuous-guided own-capital next-open branch; default offline preflight only."""
import argparse,json,hashlib,os
from pathlib import Path
from datetime import datetime,timezone
from unittest.mock import patch
from backtest.return_priority_monthly_execution_inputs_v4 import assemble_monthly_execution_inputs_v4
from backtest.continuous_guided_next_open import run_continuous_guided_next_open
from backtest.continuous_guided_account_decision import REQUIRED_PINS
from backtest.continuous_calendar_year_metrics import calendar_year_metrics

ROOT=Path(__file__).resolve().parents[1]
PREPARED='tmp/daily_verified_domain_experiment_20261016_v2/prepared.json'
EXPECTED='83f30b31b941c5a406179ae2625395794d15a1a1e1a2427876ab307d2df19921'
SPEC='research_contracts/continuous_guided_monthly_book_20261016_v1.json'
OUTPUT='tmp/continuous_guided_monthly_book_20261016_v1'
PREFLIGHT='tmp/continuous_guided_monthly_book_preflight_20261016_v1'

def stamp():return datetime.now(timezone.utc).isoformat()
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def prepare():
    path=ROOT/PREPARED
    if digest(path)!=EXPECTED:raise ValueError('SEALED_PREPARED_CHANGED')
    spec=json.loads((ROOT/SPEC).read_bytes())
    if digest(ROOT/SPEC)!='aa02f158dc720d43d10099bce05e39023531990ece95ca8d6bdd471905f471a7' or spec['schema']!='CONTINUOUS_GUIDED_MONTHLY_BOOK_EXPERIMENT_V1':raise ValueError('DECLARED_SPEC_CHANGED')
    baseline_hash='b60767394f091b5107186a01aa7747e0ef467407fc67f2901a410920ddf13e0f'
    baseline_preflight='tmp/daily_exclusion_B0_20261016_v1/preflight.json'
    original=json.loads((ROOT/baseline_preflight).read_bytes())
    if original['prepared_sha256']!=EXPECTED or any(original[k]!=v for k,v in [('initial_cash','20000'),('fee_bps','0'),('slippage_bps','0')]):raise ValueError('B0_PREFLIGHT_PARAMETERS_DIFFER')
    prepared=json.loads(path.read_bytes());pins=dict(prepared['source_hashes']);pins[SPEC]=digest(ROOT/SPEC)
    pins[baseline_preflight]=digest(ROOT/baseline_preflight)
    baseline_path='tmp/daily_exclusion_B0_20261016_v1/outcome.json'
    pins[baseline_path]=baseline_hash
    for name,h in pins.items():
        if digest(ROOT/name)!=h:raise ValueError('SOURCE_DRIFT:'+name)
    code=set(REQUIRED_PINS)|{'backtest/continuous_guided_next_open.py','backtest/current_quantity_v2_next_open_book.py',
        'backtest/current_quantity_v2_daily_next_open.py',
        'backtest/return_priority_monthly_quantity_provider_v4.py','backtest/return_priority_monthly_execution_inputs_v4.py',
        'backtest/return_priority_distribution_entitlements.py','backtest/return_priority_cash_stock_entitlements.py',
        'backtest/return_priority_ads_conversion.py','backtest/continuous_calendar_year_metrics.py',
        'scripts/run_continuous_guided_monthly_book.py'}
    added={}
    for name in sorted(code):
        h=digest(ROOT/name)
        if name in pins and pins[name]!=h:raise ValueError('CODE_PIN_CONFLICT:'+name)
        if name not in pins:added[name]=h
        pins[name]=h
    prepared['source_hashes']=pins
    assembled=assemble_monthly_execution_inputs_v4(prepared)
    if str(prepared['initial_cash'])!='20000' or str(prepared['fee_bps'])!='0':raise ValueError('B0_ECONOMIC_PARAMETERS_REQUIRED')
    args=[x['search_arguments'] for x in assembled['monthly_inputs']]
    saved_path='tmp/daily_verified_domain_experiment_20261016_v2/assembled.json'
    saved=json.loads((ROOT/saved_path).read_bytes())
    if assembled['session_dates']!=saved['session_dates'] or args!=[x['search_arguments'] for x in saved['monthly_inputs']]:raise ValueError('B0_ASSEMBLED_ARGUMENTS_DIFFER')
    pins[saved_path]=digest(ROOT/saved_path)
    if any(x['max_objective_evaluations']!=8192 for x in args):raise ValueError('B0_SEARCH_BUDGET_REQUIRED')
    receipt=dict(status='PREFLIGHT_ONLY_NO_SEARCH',prepared_path=PREPARED,prepared_sha256=EXPECTED,
        source_hashes=pins,newly_bound_current_code=added,historical_version_of_added_modules_proven=False,
        initial_cash='20000',fee_bps='0',slippage_bps='0',sessions=len(assembled['session_dates']),monthly_windows=len(args),
        all_search_arguments_equal_saved_B0_preparation=True,
        search_parameters=[{k:x[k] for k in ('decision_date','max_objective_evaluations','fixed_seed') if k in x} for x in args],
        scope='OWN_CAPITAL_FAIR_K_V2_PLUS_CONTINUOUS32_NEXT_OPEN',historical_price_basis='CONDITIONAL_RESTORED_HISTORICAL_NOMINAL_NOT_CERTIFIED',
        point_in_time_certified=False,independent_oos=False,prior_fixed_target_same_period_observed=True,limitations=spec['rules'],continuous_iterations=32,unmodeled_charges_unknown=True)
    return prepared,assembled,receipt

def main(argv=None):
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');args=parser.parse_args(argv)
    out=ROOT/(OUTPUT if args.execute else PREFLIGHT)
    # Atomic directory claim prevents concurrent/repeated economic execution.
    out.mkdir(exist_ok=False)
    def save(name,value):
        with (out/name).open('x',encoding='utf-8') as f:json.dump(value,f,indent=2)
    save('started.json',dict(at=stamp(),execute=args.execute,pid=os.getpid()))
    try:
        with patch('urllib.request.urlopen',side_effect=AssertionError('OFFLINE_EXPERIMENT')):
            prepared,assembled,receipt=prepare();save('preflight.json',receipt)
            if not args.execute:
                save('terminal.json',dict(status='PREFLIGHT_ONLY',at=stamp(),search_calls=0));print(json.dumps({k:v for k,v in receipt.items() if k not in ('source_hashes','search_parameters')}));return 0
            def progress(row):
                with (out/'progress.jsonl').open('a',encoding='utf-8') as f:
                    f.write(json.dumps(dict(row,observed_at=stamp()))+'\n');f.flush();os.fsync(f.fileno())
            result=run_continuous_guided_next_open(assembled=assembled,ohlc=prepared['ohlc'],initial_cash='20000',fee_bps='0',slippage_bps='0',progress=progress)
            save('outcome.json',result)
        if any(digest(ROOT/p)!=h for p,h in receipt['source_hashes'].items()):raise ValueError('SOURCE_CHANGED_DURING_RUN')
        if result['status']=='COMPLETE':
            yearly=calendar_year_metrics(opening_date=assembled['session_dates'][0],opening_equity='20000',daily_ledger=result['daily_ledger'],expected_sessions=assembled['session_dates'][1:],report_through=assembled['session_dates'][-1])
            for year in yearly['years']:year.pop('elapsed_day_annualized_return',None)
            save('calendar_year_metrics.json',yearly)
        save('metrics.json',dict(status=result['status'],total_return=result['total_return'],drawdown=result['drawdown'],current_minute_policy_performance=False))
        terminal=dict(status=result['status'],reason=result.get('reason'),at=stamp(),source_pins_unchanged=True,search_calls=len(result['selection_account_states']),production_changed=False)
        save('terminal.json',terminal);print(json.dumps(terminal));return 0 if result['status']=='COMPLETE' else 2
    except BaseException as error:
        save('terminal.json',dict(status='FAILED',at=stamp(),error_type=type(error).__name__,reason=str(error),automatic_retry_allowed=False));raise

if __name__=='__main__':raise SystemExit(main())
