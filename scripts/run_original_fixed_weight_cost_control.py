"""Create-only two-scenario fixed-weight control. Default preflight; no automatic retry."""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from backtest.original_fixed_weight_cost_next_open import run_original_fixed_weight_next_open
from scripts.compare_monthly_latched_exit import statistics, integer_text_limit

ROOT=Path(__file__).resolve().parents[1]
OUTPUT='tmp/original_fixed_weight_cost_control_actual_20261019_v1'
BASE='tmp/daily_verified_domain_experiment_20261016_v2/assembled.json'
SCENARIOS={'slippage5':{'fee_bps':'0','slippage_bps':'5'},'fee1_slippage10':{'fee_bps':'1','slippage_bps':'10'}}


@integer_text_limit()
def run(*,contract_path,contract_sha256,execute=False):
    path=Path(contract_path).resolve()
    if not path.is_relative_to(ROOT):raise ValueError('WORKSPACE_CONTRACT_REQUIRED')
    raw=path.read_bytes()
    if sha256(raw).hexdigest()!=contract_sha256:raise ValueError('CONTRACT_HASH_MISMATCH')
    contract=json.loads(raw)
    source=(ROOT/contract['inputs_path']).resolve()
    if not source.is_relative_to(ROOT):raise ValueError('WORKSPACE_INPUT_REQUIRED')
    raw=source.read_bytes()
    if sha256(raw).hexdigest()!=contract['inputs_sha256']:raise ValueError('INPUT_HASH_MISMATCH')
    bundle=json.loads(raw)
    pins=dict(bundle['source_hashes'])
    for name,value in contract['new_source_hashes'].items():
        if name in pins and pins[name]!=value:raise ValueError('PIN_CONFLICT')
        pins[name]=value
    required={BASE,'scripts/run_original_fixed_weight_cost_control.py','backtest/original_fixed_weight_cost_next_open.py','scripts/compare_monthly_latched_exit.py'}
    if not required <= pins.keys():raise ValueError('RUNNER_PINS_REQUIRED')
    def check():
        for name,expected in pins.items():
            p=(ROOT/name).resolve()
            if not p.is_relative_to(ROOT) or sha256(p.read_bytes()).hexdigest()!=expected:raise ValueError('SOURCE_DRIFT')
    check()
    baseline=json.loads((ROOT/BASE).read_bytes())
    if contract.get('event_scope')!='SEALED_FULL_DOMAIN' or bundle['assembled'].get('original_control_action_scope',{}).get('active_policy')!='SEALED_FULL_DOMAIN':raise ValueError('SEALED_FULL_EVENT_SCOPE_REQUIRED')
    if any(bundle['assembled'].get(field)!=baseline.get(field) for field in ('actions','provider_actions','cash_stock_merger_events','distribution_events','fractional_settlements','distribution_fractional_cash_values','account_model')):raise ValueError('SEALED_EVENT_INPUT_MISMATCH')
    if contract['scenarios']!=SCENARIOS or bundle['scenarios']!=SCENARIOS or contract['initial_cash']!='20000' or bundle['initial_cash']!='20000' or contract['weights']!=bundle['weights'] or contract['total_maximum_books']!=2 or contract['maximum_search_calls']!=0 or contract['automatic_retry'] is not False:
        raise ValueError('DECLARED_CONTROL_MISMATCH')
    if contract.get('output_directory')!=OUTPUT:raise ValueError('FIXED_OUTPUT_REQUIRED')
    if not execute:return dict(status='PREFLIGHT_ONLY_NO_BOOK',source_count=len(pins))
    if contract.get('execution_authorized') is not True:raise ValueError('RUN_REGISTRATION_REQUIRED')
    directory=ROOT/OUTPUT;directory.mkdir(parents=True,exist_ok=False)
    def save(name,value):
        with (directory/name).open('x',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False)
    save('started.json',dict(contract_sha256=contract_sha256,status='STARTED_NO_RETRY'))
    try:
        for scenario,cost in SCENARIOS.items():
            check()
            assembled=deepcopy(bundle['assembled'])
            for plan in assembled['monthly_inputs']:plan['search_arguments']['fee_bps']=cost['fee_bps']
            outcome=run_original_fixed_weight_next_open(weights=bundle['weights'],assembled=assembled,ohlc=bundle['ohlc'],initial_cash='20000',**cost)
            save(scenario+'.outcome.json',outcome)
            if outcome['status']!='COMPLETE':raise ValueError('CONTROL_BOOK_BLOCKED')
            save(scenario+'.metrics.json',statistics(outcome,assembled['session_dates']))
        check();save('terminal.json',dict(status='COMPLETE',book_calls=2,search_calls=0))
    except Exception:
        save('failed.json',dict(status='FAILED_REVIEW_REQUIRED_NO_RETRY'));raise
    return dict(status='COMPLETE',book_calls=2,search_calls=0)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--contract-path',required=True);parser.add_argument('--contract-sha256',required=True);parser.add_argument('--execute',action='store_true')
    print(json.dumps(run(**vars(parser.parse_args()))))


if __name__=='__main__':main()
