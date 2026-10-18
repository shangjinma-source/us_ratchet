"""Exploratory same-calendar whole-share candidate/control/NAV comparison.

This does not establish complete dividends/split coverage or admission. The NAV
index is native-currency, not a simulated executable USD fund investment.
"""
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backtest import ndx_joint_weight_runner as encoding
from scripts.ndx_joint_weight_verify import _restore_input
from scripts.ndx_next_session_execution_probe import run as candidate_probe
from backtest.ndx_execution_nominal_bundle_research import load_execution_nominal_bundle
from backtest.ndx_incumbent_risk_overlay_research import load_incumbent_risk_overlay
from backtest.ndx_nominal_event_diagnostics_research import diagnose_nominal_events
from backtest.ndx_incumbent_execution_control_research import simulate_fixed_weight_incumbent_control
from backtest.ndx_integer_allocation_research import RISK_FIELDS

BASE = ROOT/'data/cache/research/ndx_joint_weight_experiment_v2'
COMPARISON_SHA = '4a393917f4558e67b756705d783d95e78aee8eb2e43729b77848114d3edbec6f'
_LOADED_PROBE_SHA = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def run():
    if hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != _LOADED_PROBE_SHA:
        raise ValueError('Probe source changed since import')
    observed = {}
    def register(mapping):
        for path, digest in mapping.items():
            path = Path(path)
            if not path.is_absolute():
                path = ROOT/path
            key = str(path.resolve())
            if key in observed and observed[key] != digest:
                raise ValueError('Conflicting source binding')
            observed[key] = digest
    def read(path, expected):
        path = Path(path)
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError('Input identity differs: '+str(path))
        observed[str(path)] = expected
        return json.loads(raw)

    own_sha = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    comparison_path = BASE/'integer_execution_comparison_20260911.json'
    comparison = read(comparison_path, COMPARISON_SHA)
    context_path = ROOT/'data/cache/research/ndx_joint_weight_runs_v2'/comparison['context_sha256']/'context.json'
    context_raw = context_path.read_bytes()
    context = json.loads(context_raw)
    if encoding._sha(context) != comparison['context_sha256'] or encoding._json_bytes(context) != context_raw:
        raise ValueError('Context identity differs')
    observed[str(context_path)] = hashlib.sha256(context_raw).hexdigest()
    inputs = {k:_restore_input(v) for k,v in context['prepared_inputs'].items()}
    calendar = inputs['nominal_prices'].loc[comparison['date_start']:comparison['date_end']].index
    selected = [t for t in context['tasks'] if t['job_id'] == comparison['job_id']]
    if len(selected) != 1:
        raise ValueError('Ambiguous candidate task')
    candidate_names = sorted(selected[0]['tickers'].split(';'))
    weights = inputs['incumbent_weights']
    combined = sorted(set(candidate_names) | set(weights))
    bundle = load_execution_nominal_bundle(
        inventory_path=ROOT/'data/cache/research/ndx_cardinality_execution_prices_walkforward_v2/execution_price_inventory.csv',
        expected_inventory_sha256='6e16c3fea22421e650663f617e2bf2d6c6cc87db52bf1303f7a3380e6b600961',
        tickers=combined, execution_calendar=calendar)
    prices = bundle.pop('prices')
    register({bundle['inventory_path']:bundle['inventory_sha256']})
    for evidence in bundle['evidence']:
        register({evidence['path']:evidence['sha256'],evidence['sidecar_path']:evidence['sidecar_sha256']})
    if not prices[candidate_names].equals(inputs['nominal_prices'].loc[calendar, candidate_names]):
        raise ValueError('Candidate execution prices differ')
    split_proof = read(BASE/'split_execution_probe_20260911.json',
        'b45a140d815dff0876938dc2035c894e06ade527c1c11b58928f16dccfe39d32')
    events = [r['event'] for day in split_proof['new_with_explicit_split']['corporate_action_ledger']
              for r in day['applied_events']]
    for path, digest in split_proof['source_hashes'].items():
        raw = Path(path).read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError('Split review input changed')
        observed[path] = digest
    diagnostics = diagnose_nominal_events(prices=prices, execution_calendar=calendar,
        split_events=events, jump_ratio_threshold=.5)
    # The fixed prior candidate has no declared event; its v1 path cannot be
    # reused if an event or an unexplained large jump affects that candidate.
    if any(e['ticker'] in candidate_names for e in events) or diagnostics['unmatched_jumps']:
        raise ValueError('Candidate/control event review required before this explicit probe')
    risk = load_incumbent_risk_overlay(
        reviewed_manifest_path=ROOT/'data/cache/candidate_pools/ndx_taxonomy_v2/incumbent_overlay/reviewed/manifest.json',
        expected_manifest_sha256='8ab02a983a5b316b0da053d3f97dd87f87b863a36a4f359a5ab23b74700b384b',
        tickers=sorted(weights), date_start=comparison['date_start'], date_end=comparison['date_end'])
    register(risk['provenance']['source_hashes'])
    risk['evidence_row_count'] = len(risk.pop('evidence'))
    risk['evidence_excerpts_omitted_from_export'] = True
    candidate_result = candidate_probe(comparison_path, COMPARISON_SHA)
    candidate = next(p for p in candidate_result['paths'] if p['selection_policy'] == 'TRACKING_FIRST')
    register(candidate['source_hashes'])
    register(comparison['numerical_sources'])
    register(comparison['source_hashes'])
    register({str(ROOT/'scripts/ndx_next_session_execution_probe.py'):candidate_result['probe_source_sha256']})
    contract = inputs['contract']
    control = simulate_fixed_weight_incumbent_control(prices=prices[sorted(weights)],
        execution_calendar=calendar, decision_dates=[r['execution_date'] for r in comparison['periodic_clock']['schedule']],
        incumbent_weights=weights, corporate_actions=events, initial_cash=contract['portfolio_cash_usd'],
        initial_shares={t:0 for t in weights}, minimum_cash_buffer_usd=contract['minimum_cash_buffer_usd'],
        transaction_cost_bps=contract['transaction_cost_bps'], risk_chain_by_ticker=risk['risk_chain_by_ticker'],
        constraints={k:contract[k] for k in RISK_FIELDS}, domain_radius=2, max_evaluations_per_rebalance=1000000)
    register(control['source_hashes'])
    register(diagnostics['source_hashes'])
    register({str(ROOT/'backtest/ndx_execution_nominal_bundle_research.py'):bundle['loader_source_sha256']})
    expected_dates = list(calendar.strftime('%Y-%m-%d'))
    if any([r['date'] for r in path['daily']] != expected_dates or
           path['initial_equity_usd'] != contract['portfolio_cash_usd'] for path in (candidate,control)):
        raise ValueError('Execution interval or starting capital differs')
    returns = inputs['target_returns'].loc[calendar]
    nav = [1.]
    for value in returns.iloc[1:]:
        if not math.isfinite(float(value)) or float(value) < -1:
            raise ValueError('Invalid NAV return')
        nav.append(nav[-1]*(1+float(value)))
    peak, drawdown = 1., 0.
    for value in nav:
        peak = max(peak, value)
        drawdown = max(drawdown, 1-value/peak)
    periods = len(calendar)-1
    if periods <= 0 or not all(math.isfinite(v) and v >= 0 for v in nav):
        raise ValueError('Invalid benchmark path')
    def compact(path):
        return {**{k:v for k,v in path.items() if k not in ('daily',)},
            'daily_equity_usd':[r['equity_usd'] for r in path['daily']],
            'full_daily_risk_rows_omitted':True,
            'annualized_return_252_session':(path['terminal_equity_usd']/path['initial_equity_usd'])**(252/periods)-1}
    if (hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != own_sha or any(
            hashlib.sha256(Path(p).read_bytes()).hexdigest() != h for p,h in observed.items())):
        raise ValueError('Probe source/input drift')
    return dict(schema='ndx_same_execution_dual_benchmark_probe_v1', source_hashes=observed,
        probe_sha256=own_sha, context_sha256=comparison['context_sha256'], job_id=comparison['job_id'],
        date_start=comparison['date_start'],date_end=comparison['date_end'],calendar=list(calendar.strftime('%Y-%m-%d')),
        candidate=compact(candidate), incumbent=compact(control), nominal_bundle=bundle,
        risk_overlay=risk, nominal_event_diagnostics=diagnostics,
        nav_benchmark=dict(role='012922_NATIVE_CURRENCY_NAV_INDEX_NONEXECUTABLE',equity_index=nav,
            path_return=nav[-1]-1, path_max_drawdown=drawdown,
            annualized_return_252_session=nav[-1]**(252/periods)-1,
            first_session_return_excluded=True,subscription_redemption_fees_modelled=False,fx_modelled=False),
        annualization_convention='252_PER_OBSERVED_RETURN_PERIOD',return_period_count=periods,
        research_scope='FIXED_HISTORICAL_COORDINATE_EXPLORATORY_NOT_FULL_JOINT_ENVELOPE',
        corporate_action_coverage_verified=False,cash_dividends_modelled=False,
        promotion_allowed=False,order_generation_allowed=False)


if __name__ == '__main__':
    report = run()
    def metrics(path):
        keys = ('status','initial_equity_usd','terminal_equity_usd','terminal_cash_usd',
            'terminal_shares','total_fees_usd','path_return_net','path_max_drawdown',
            'annualized_return_252_session','risk_failure_days','trade_execution_count',
            'rejected_execution_count','cancelled_pending_plan_count','any_partial_search')
        return {**{k:path[k] for k in keys if k in path},
            'daily_equity_usd':path['daily_equity_usd'],
            'decision_ledger_sha256':encoding._sha(path['decisions']),
            'execution_ledger_sha256':encoding._sha(path['executions'])}
    print(json.dumps(dict(schema='ndx_same_execution_dual_benchmark_compact_v1',
        full_report_sha256=encoding._sha(report),full_report_omitted_from_export=True,
        source_identity_sha256=encoding._sha(report['source_hashes']),source_count=len(report['source_hashes']),
        probe_sha256=report['probe_sha256'],context_sha256=report['context_sha256'],job_id=report['job_id'],
        date_start=report['date_start'],date_end=report['date_end'],return_period_count=report['return_period_count'],
        annualization_convention=report['annualization_convention'],
        candidate=metrics(report['candidate']),incumbent=metrics(report['incumbent']),
        nav_benchmark=report['nav_benchmark'],
        nominal_jump_count=len(report['nominal_event_diagnostics']['jumps']),
        unmatched_jump_count=len(report['nominal_event_diagnostics']['unmatched_jumps']),
        corporate_action_coverage_verified=False,cash_dividends_modelled=False,
        promotion_allowed=False,order_generation_allowed=False),indent=2))
