"""Exploratory execution recheck of explicit frozen v3 diagnostic cases.

No live inputs are changed. Empty declared actions are NOT verified coverage.
run() returns full ledgers; CLI prints a compact digest, not a durable checkpoint.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.ndx_v3_execution_recheck_plan import CASES, prepare_case
from backtest import ndx_joint_weight_runner as encoding
from backtest.ndx_execution_nominal_bundle_research import load_execution_nominal_bundle
from backtest.ndx_incumbent_risk_overlay_research import load_incumbent_risk_overlay
from backtest.ndx_nominal_event_diagnostics_research import diagnose_nominal_events
from backtest.ndx_next_session_execution_research_v2 import simulate_next_session_execution_research_v2
from backtest.ndx_incumbent_execution_control_research_v2 import simulate_fixed_weight_incumbent_control_v2
from backtest.ndx_integer_allocation_research import RISK_FIELDS

_PATHS = [Path(__file__).resolve()] + [ROOT / path for path in (
    'scripts/ndx_v3_execution_recheck_plan.py',
    'backtest/ndx_execution_nominal_bundle_research.py',
    'backtest/ndx_incumbent_risk_overlay_research.py',
    'backtest/ndx_nominal_event_diagnostics_research.py')]
_LOADED = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in _PATHS}


def _check_sources(observed):
    if any(hashlib.sha256(Path(path).read_bytes()).hexdigest() != digest
           for path, digest in observed.items()):
        raise ValueError('Source/input changed since import or capture')


def nav_path(returns, calendar):
    if not returns.index.equals(calendar) or len(calendar) < 2:
        raise ValueError('NAV calendar differs or has no return interval')
    values = [1.]
    for value in returns.iloc[1:]:
        if isinstance(value, bool) or not math.isfinite(float(value)) or float(value) < -1:
            raise ValueError('Invalid NAV return')
        values.append(values[-1] * (1 + float(value)))
    if not all(math.isfinite(value) and value >= 0 for value in values):
        raise ValueError('Invalid NAV path')
    peak, drawdown = 1., 0.
    for value in values:
        peak = max(peak, value)
        drawdown = max(drawdown, 1 - value / peak)
    return dict(role='012922_NATIVE_CURRENCY_NAV_INDEX_NONEXECUTABLE', equity_index=values,
        path_return=values[-1]-1, path_max_drawdown=drawdown,
        annualized_return_252_session=values[-1]**(252/(len(calendar)-1))-1,
        first_session_return_excluded=True, subscription_redemption_fees_modelled=False,
        fx_modelled=False)


def run(case_index=0):
    if type(case_index) is not int or not 0 <= case_index < len(CASES):
        raise ValueError('Explicit case index out of range')
    _check_sources(_LOADED)
    prepared = prepare_case(*CASES[case_index])
    summary, inputs = prepared['summary'], prepared['inputs']
    candidate_prices = prepared['prices']
    calendar = candidate_prices.index
    names = list(candidate_prices.columns)
    weights = inputs['incumbent_weights']
    combined = sorted(set(names) | set(weights))
    observed = dict(_LOADED)

    def register(mapping):
        for path, digest in mapping.items():
            path = Path(path)
            key = str((path if path.is_absolute() else ROOT/path).resolve())
            if key in observed and observed[key] != digest:
                raise ValueError('Conflicting source identity')
            observed[key] = digest

    register(summary['source_hashes'])
    bundle = load_execution_nominal_bundle(
        inventory_path=ROOT/'data/cache/research/ndx_cardinality_execution_prices_walkforward_v2/execution_price_inventory.csv',
        expected_inventory_sha256='6e16c3fea22421e650663f617e2bf2d6c6cc87db52bf1303f7a3380e6b600961',
        tickers=combined, execution_calendar=calendar)
    prices = bundle.pop('prices')
    register({bundle['inventory_path']: bundle['inventory_sha256']})
    for item in bundle['evidence']:
        register({item['path']: item['sha256'], item['sidecar_path']: item['sidecar_sha256']})
    if not prices[names].equals(candidate_prices):
        raise ValueError('Candidate prices differ from frozen context')
    events = []
    diagnostics = diagnose_nominal_events(prices=prices, execution_calendar=calendar,
        split_events=events, jump_ratio_threshold=.5)
    if diagnostics['unmatched_jumps']:
        raise ValueError('Unmatched nominal jump requires reviewed corporate action evidence')
    register(diagnostics['source_hashes'])
    risk = load_incumbent_risk_overlay(
        reviewed_manifest_path=ROOT/'data/cache/candidate_pools/ndx_taxonomy_v2/incumbent_overlay/reviewed/manifest.json',
        expected_manifest_sha256='8ab02a983a5b316b0da053d3f97dd87f87b863a36a4f359a5ab23b74700b384b',
        tickers=sorted(weights), date_start=summary['date_start'], date_end=summary['date_end'])
    register(risk['provenance']['source_hashes'])
    contract = inputs['contract']
    schedule = [(row['execution_date'], row['weights']) for row in prepared['clock']['schedule']]
    common = dict(execution_calendar=calendar, corporate_actions=events,
        initial_cash=contract['portfolio_cash_usd'],
        minimum_cash_buffer_usd=contract['minimum_cash_buffer_usd'],
        transaction_cost_bps=contract['transaction_cost_bps'],
        constraints={key: contract[key] for key in RISK_FIELDS}, domain_radius=2,
        max_evaluations_per_rebalance=1000000)
    _check_sources(observed)
    candidate = simulate_next_session_execution_research_v2(prices=candidate_prices,
        schedule=schedule, initial_shares={name: 0 for name in names}, selection_policy='TRACKING_FIRST',
        risk_chain_by_ticker=inputs['universe'].set_index('ticker').loc[names, 'risk_chain'].to_dict(), **common)
    control = simulate_fixed_weight_incumbent_control_v2(prices=prices[sorted(weights)],
        decision_dates=[date for date, _ in schedule], incumbent_weights=weights,
        initial_shares={name: 0 for name in weights},
        risk_chain_by_ticker=risk['risk_chain_by_ticker'], **common)
    expected_dates = list(calendar.strftime('%Y-%m-%d'))
    for path in (candidate, control):
        register(path['source_hashes'])
        if ([row['date'] for row in path['daily']] != expected_dates
                or path['initial_equity_usd'] != contract['portfolio_cash_usd']):
            raise ValueError('Execution calendar or initial capital differs')
        path['annualized_return_252_session'] = (
            path['terminal_equity_usd']/path['initial_equity_usd'])**(252/(len(calendar)-1))-1
    benchmark = nav_path(inputs['target_returns'].loc[calendar], calendar)
    _check_sources(observed)
    return dict(schema='ndx_v3_same_execution_recheck_v1', case_index=case_index,
        preparation=summary, periodic_clock=prepared['clock'], calendar=expected_dates,
        inherited_context_capital_usd=contract['portfolio_cash_usd'],
        capital_scope='FROZEN_CONTEXT_COMPARABILITY_NOT_CURRENT_USER_AVAILABLE_CAPITAL',
        capital_sensitivity_performed=False, current_user_holdings_simulated=False,
        candidate=candidate, incumbent=control, nav_benchmark=benchmark,
        nominal_bundle=bundle, risk_overlay=risk, nominal_event_diagnostics=diagnostics,
        source_hashes=observed, return_period_count=len(calendar)-1,
        annualization_convention='252_PER_OBSERVED_RETURN_PERIOD',
        corporate_actions=events, corporate_action_coverage_verified=False,
        cash_dividends_modelled=False, external_source_authenticity_verified=False,
        current_point_in_time_eligibility_verified=False,
        research_scope='FIXED_HISTORICAL_DIAGNOSTIC_NOT_GLOBAL_PORTFOLIO_OPTIMUM',
        portfolio_role='portfolio_optimization_DIAGNOSTIC_NOT_migration_control',
        full_joint_envelope_verified=False, admission_allowed=False,
        portfolio_selection_precedes_execution=False,
        retrospective_fixed_portfolio_diagnostic=True, fresh_oos_consumed=False,
        promotion_allowed=False, order_generation_allowed=False)


def compact(report):
    def metrics(path):
        keys = ('status', 'initial_equity_usd', 'terminal_equity_usd', 'terminal_cash_usd',
            'terminal_shares', 'total_fees_usd', 'path_return_net', 'path_max_drawdown',
            'annualized_return_252_session', 'risk_failure_days', 'trade_execution_count',
            'rejected_execution_count', 'cancelled_pending_plan_count', 'any_partial_search')
        return dict(**{key: path[key] for key in keys if key in path},
            daily_ledger_sha256=encoding._sha(path['daily']),
            decision_ledger_sha256=encoding._sha(path['decisions']),
            execution_ledger_sha256=encoding._sha(path['executions']))
    return dict(schema='ndx_v3_same_execution_recheck_compact_v1',
        full_report_sha256=encoding._sha(report), full_report_omitted_from_stdout=True,
        full_report_persisted_by_cli=False, case_index=report['case_index'],
        context_sha256=report['preparation']['context_sha256'], job_id=report['preparation']['job_id'],
        date_start=report['calendar'][0], date_end=report['calendar'][-1],
        inherited_context_capital_usd=report['inherited_context_capital_usd'],
        capital_scope=report['capital_scope'],
        portfolio_selection_precedes_execution=report['portfolio_selection_precedes_execution'],
        retrospective_fixed_portfolio_diagnostic=report['retrospective_fixed_portfolio_diagnostic'],
        fresh_oos_consumed=report['fresh_oos_consumed'],
        candidate=metrics(report['candidate']), incumbent=metrics(report['incumbent']),
        nav_benchmark={key: value for key, value in report['nav_benchmark'].items() if key != 'equity_index'},
        corporate_action_coverage_verified=False, admission_allowed=False, promotion_allowed=False)


def run_and_export(case_index=0, output_path=None):
    destination = None
    if output_path is not None:
        destination = Path(output_path).resolve()
        research_root = (ROOT/'data/cache/research').resolve()
        if (not destination.is_relative_to(research_root) or destination == research_root
                or destination.suffix != '.json' or not destination.parent.is_dir()):
            raise ValueError('Output must be an explicit JSON file under existing research directory')
        if destination.exists():
            raise ValueError('Output already exists; refusing replay or overwrite')
    report = run(case_index)
    result = compact(report)
    if destination is not None:
        if destination.exists():
            raise ValueError('Output appeared during replay; refusing overwrite')
        encoding._publish(destination, report)
        if destination.read_bytes() != encoding._json_bytes(report):
            raise ValueError('Published full report differs')
        result.update(full_report_persisted_by_cli=True, full_report_path=str(destination))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case-index', type=int, default=0)
    parser.add_argument('--output-path')
    arguments = parser.parse_args()
    print(json.dumps(run_and_export(arguments.case_index, arguments.output_path), indent=2))
