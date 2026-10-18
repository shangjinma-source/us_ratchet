"""One isolated adaptive premium branch; default offline preflight only."""
import argparse,json,hashlib,os
from pathlib import Path
from datetime import datetime,timezone
from unittest.mock import patch
from backtest.return_priority_monthly_execution_inputs_v4 import assemble_monthly_execution_inputs_v4
from backtest.adaptive_daily_sell_premium import run_adaptive_daily_premium
from data.current_research_capital_decision_v2 import REQUIRED_PINS
from backtest.continuous_calendar_year_metrics import calendar_year_metrics

ROOT=Path(__file__).resolve().parents[1]
PREPARED='tmp/daily_verified_domain_experiment_20261016_v2/prepared.json'
EXPECTED='83f30b31b941c5a406179ae2625395794d15a1a1e1a2427876ab307d2df19921'
SPEC='research_contracts/adaptive_daily_sell_comparison_20261016_v1.json'
OUTPUT='tmp/adaptive_daily_sell_premium_20261016_v1'
PREFLIGHT='tmp/adaptive_daily_sell_premium_preflight_20261016_v2'

def stamp():return datetime.now(timezone.utc).isoformat()
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def prepare():
    path=ROOT/PREPARED
    if digest(path)!=EXPECTED:raise ValueError('SEALED_PREPARED_CHANGED')
    spec=json.loads((ROOT/SPEC).read_bytes())
    if spec['schema']!='ADAPTIVE_DAILY_SELL_COMPARISON_V1' or spec['prepared_sha256']!=EXPECTED or any(spec[k]!=v for k,v in [('initial_cash','20000'),('fee_bps','0'),('slippage_bps','0')]):raise ValueError('DECLARED_SPEC_PARAMETER_MISMATCH')
    if digest(ROOT/'tmp/daily_exclusion_B0_20261016_v1/outcome.json')!=spec['baseline_outcome_sha256']:raise ValueError('SEALED_BASELINE_CHANGED')
    baseline_preflight='tmp/daily_exclusion_B0_20261016_v1/preflight.json'
    original=json.loads((ROOT/baseline_preflight).read_bytes())
    if original['prepared_sha256']!=EXPECTED or any(original[k]!=spec[k] for k in ('initial_cash','fee_bps','slippage_bps')):raise ValueError('B0_PREFLIGHT_PARAMETERS_DIFFER')
    prepared=json.loads(path.read_bytes());pins=dict(prepared['source_hashes']);pins[SPEC]=digest(ROOT/SPEC)
    pins[baseline_preflight]=digest(ROOT/baseline_preflight)
    baseline_path='tmp/daily_exclusion_B0_20261016_v1/outcome.json'
    pins[baseline_path]=spec['baseline_outcome_sha256']
    for name,h in pins.items():
        if digest(ROOT/name)!=h:raise ValueError('SOURCE_DRIFT:'+name)
    code=set(REQUIRED_PINS)|{'backtest/adaptive_daily_sell_premium.py','backtest/current_quantity_v2_daily_sell_book.py',
        'backtest/daily_sell_switch_execution.py','backtest/current_quantity_v2_daily_next_open.py',
        'backtest/return_priority_monthly_quantity_provider_v4.py','backtest/return_priority_monthly_execution_inputs_v4.py',
        'backtest/return_priority_distribution_entitlements.py','backtest/return_priority_cash_stock_entitlements.py',
        'backtest/return_priority_ads_conversion.py','backtest/continuous_calendar_year_metrics.py',
        'scripts/run_adaptive_daily_sell_premium.py'}
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
        search_parameters=[{k:x[k] for k in ('decision_date','max_objective_evaluations','seed') if k in x} for x in args],
        scope='ADAPTIVE_V2_DAILY_PREMIUM_NOT_CURRENT_MINUTE_POLICY',historical_price_basis='CONDITIONAL_RESTORED_HISTORICAL_NOMINAL_NOT_CERTIFIED',
        point_in_time_certified=False,independent_oos=False,prior_fixed_target_same_period_observed=True,limitations=spec['limitations'],unmodeled_charges_unknown=True)
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
            result=run_adaptive_daily_premium(assembled=assembled,ohlc=prepared['ohlc'],initial_cash='20000',fee_bps='0',slippage_bps='0',progress=progress)
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
