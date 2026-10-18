"""One-shot frozen-target accounting comparison; never rerun stock selection."""
import json
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backtest.return_priority_monthly_execution_inputs_v4 import assemble_monthly_execution_inputs_v4
from backtest.frozen_target_daily_sell_experiment import run_frozen_targets


def main():
    out = ROOT/'tmp/frozen_target_daily_sell_20261016_v2'
    out.mkdir(exist_ok=False)
    def save(name, value):
        (out/name).write_text(json.dumps(value, indent=2), encoding='utf-8')
    save('started.json', dict(at=datetime.now(timezone.utc).isoformat(), strategy_search_calls=0))
    try:
        prepared_path = ROOT/'tmp/daily_verified_domain_experiment_20261016_v2/prepared.json'
        baseline_path = ROOT/'tmp/daily_exclusion_B0_20261016_v1/outcome.json'
        expected = {
            prepared_path: '83f30b31b941c5a406179ae2625395794d15a1a1e1a2427876ab307d2df19921',
            baseline_path: 'b60767394f091b5107186a01aa7747e0ef467407fc67f2901a410920ddf13e0f',
        }
        for path, digest in expected.items():
            if sha256(path.read_bytes()).hexdigest() != digest:
                raise ValueError('FROZEN_INPUT_CHANGED:'+str(path))
        prepared = json.loads(prepared_path.read_bytes())
        baseline = json.loads(baseline_path.read_bytes())
        if baseline['status'] != 'COMPLETE':
            raise ValueError('BASELINE_INCOMPLETE')
        dependencies = [
            'backtest/return_priority_monthly_execution_inputs_v4.py',
            'backtest/return_priority_monthly_quantity_provider_v4.py',
            'backtest/current_quantity_v2_next_open_book.py',
            'backtest/return_priority_ads_conversion.py',
            'backtest/return_priority_distribution_entitlements.py',
            'backtest/return_priority_cash_stock_entitlements.py',
        ]
        newly_bound_support = []
        for name in dependencies:
            if name not in prepared['source_hashes']:
                if name not in ('backtest/return_priority_distribution_entitlements.py',
                                'backtest/return_priority_cash_stock_entitlements.py'):
                    raise ValueError('UNPINNED_ACCOUNTING_DEPENDENCY:'+name)
                newly_bound_support.append(name)
                continue
            if sha256((ROOT/name).read_bytes()).hexdigest() != prepared['source_hashes'][name]:
                raise ValueError('ACCOUNTING_SOURCE_DRIFT:'+name)
        new_code = ['backtest/current_quantity_v2_daily_sell_book.py',
                    'backtest/daily_sell_switch_execution.py',
                    'backtest/frozen_target_daily_sell_experiment.py',
                    'scripts/run_frozen_target_daily_sell_experiment.py']
        save('inputs.json', dict(frozen_inputs={str(p.relative_to(ROOT)):h for p,h in expected.items()},
                                code_hashes={p:sha256((ROOT/p).read_bytes()).hexdigest() for p in dependencies+new_code},
                                newly_bound_support_not_historically_pinned=newly_bound_support,
                                historical_code_identity_proven=False,
                                spec='tmp/daily_sell_pair_20261016_v1/continuous_account_plan.json'))
        with patch('urllib.request.urlopen', side_effect=AssertionError('NO_NETWORK_EXPERIMENT')):
            assembled = assemble_monthly_execution_inputs_v4(prepared)
            reference = run_frozen_targets(assembled=assembled, ohlc=prepared['ohlc'],
                                          baseline=baseline, initial_cash=prepared['initial_cash'], mode='BASELINE_OPEN')
            save('baseline_reconciliation.json', reference)
            keys = ['daily_ledger', 'cash', 'shares', 'fees', 'receivable', 'merger_entitlements',
                    'distribution_rights', 'after_close_records', 'final_wealth_basis']
            matches = {key:reference[key] == baseline[key] for key in keys}
            save('reconciliation_checks.json', matches)
            if reference['status'] != 'COMPLETE' or not all(matches.values()):
                raise ValueError('BASELINE_ACCOUNTING_RECONCILIATION_FAILED')
            premium = run_frozen_targets(assembled=assembled, ohlc=prepared['ohlc'],
                                        baseline=baseline, initial_cash=prepared['initial_cash'], mode='PREMIUM_DAY')
            save('premium.json', premium)
        save('terminal.json', dict(status=premium['status'], reason=premium.get('reason'),
                                  state_date=premium['state_date'], strategy_search_calls=0,
                                  adaptive_strategy_performance=False, production_changed=False))
        print((out/'terminal.json').read_text())
    except Exception as error:
        save('terminal.json', dict(status='FAILED', reason=str(error), strategy_search_calls=0))
        raise


if __name__ == '__main__':
    main()
