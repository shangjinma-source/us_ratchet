"""Read-only, single-source historical overlap probe; not a production loader.

Current evaluator/spec are explicitly a new experiment. No source equivalence,
admission, cross-ticker support, or durable runner completion is claimed.
"""
import hashlib
import argparse
import io
import json
import math
from pathlib import Path
import sys

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backtest.ndx_cardinality_capital_replay_summary import _exact_historical_csv_prefix
from backtest.ndx_cardinality_discovery import evaluate_synthetic_portfolio


def run(*, revised_return_experiment=False, all_equal_controls=False, holding_count=1,
        include_weight_controls=False, return_prepared=False):
    evidence = []
    source_paths = [Path(__file__).resolve(), ROOT/'backtest/ndx_cardinality_discovery.py',
                    ROOT/'backtest/ndx_whole_lot_rebalance.py', ROOT/'backtest/weights.py',
                    ROOT/'config/ndx_cardinality_discovery_v1.yaml']
    source_hashes = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in source_paths}

    def read(descriptor, *, prefix=False, allow_revised=False):
        path = Path(descriptor['path'])
        raw = path.read_bytes()
        observed = hashlib.sha256(raw).hexdigest()
        recovery = 'EXACT_FILE'
        if observed != descriptor['sha256']:
            recovered = _exact_historical_csv_prefix(raw, descriptor['sha256'], str(path)) if prefix else None
            if recovered is not None:
                raw = recovered
                recovery = 'EXACT_PREFIX'
            elif allow_revised:
                recovery = 'REVISED_RETURN_DATA_NEW_EXPERIMENT_ONLY'
            else:
                raise ValueError(f'Unrecoverable source: {path}')
        evidence.append(dict(path=str(path), sha256=hashlib.sha256(raw).hexdigest(),
                             expected_historical_sha256=descriptor['sha256'],
                             recovery_status=recovery, observed_sha256=observed, bytes=len(raw)))
        return raw

    def frame(descriptor, *, prefix=False, allow_revised=False):
        return pd.read_csv(io.BytesIO(read(descriptor, prefix=prefix, allow_revised=allow_revised)), keep_default_na=False)

    def bars(descriptor, *, prefix=False, allow_revised=False):
        value = frame(descriptor, prefix=prefix, allow_revised=allow_revised)
        value['Date'] = pd.to_datetime(value['Date'], errors='raise')
        if value.Date.duplicated().any() or not value.Date.is_monotonic_increasing:
            raise ValueError('Invalid bar dates')
        for key in ('Close', 'Volume'):
            if key in value:
                value[key] = pd.to_numeric(value[key], errors='raise')
        return value.set_index('Date')

    screen_path = ROOT / 'data/cache/research/ndx_one_sided_envelope_diagnostic_20260911/original_strict_screen.json'
    screen_raw = screen_path.read_bytes()
    coordinates = [item for item in json.loads(screen_raw)['rows']
                   if item['date'] == '2023-04-03' and item['k'] == holding_count]
    if type(holding_count) is not int or holding_count <= 0 or len(coordinates) != 1:
        raise ValueError('Probe requires an existing unique April 2023 coordinate')
    coordinate = coordinates[0]
    child_path = Path(coordinate['child_manifest_path'])
    child = json.loads(read(dict(path=str(child_path), sha256=coordinate['child_manifest_sha256'])))
    if (child['selection_date'], child['holding_count']) != ('2023-04-03', holding_count):
        raise ValueError('Probe coordinate mismatch')
    # This ancestor manifest is observed locally, not an externally authenticated root.
    run_raw = (child_path.parents[5] / 'manifest.json').read_bytes()
    source_run = json.loads(run_raw)
    discovery = json.loads(read(source_run['inputs']['discovery_manifest']))
    membership = frame(child['inputs']['membership_audit'])
    identity = frame(child['inputs']['identity_audit'])
    members = frame(discovery['artifacts']['eligible_securities'])
    selection = pd.Timestamp(child['selection_date'])
    track = child['universe_track']
    mask = lambda f: f.selection_date.eq(child['selection_date']) & f.universe_track.eq(track)
    ready = membership.loc[mask(membership) & membership.input_ready.eq(True), ['security_id']]
    universe = members.loc[mask(members) & members.membership_window_eligible.eq(True)].merge(
        ready, on='security_id', validate='one_to_one')
    inventory = frame(child['artifacts']['price_inventory'])
    if inventory.cross_ticker_stitched.eq(True).any() or not inventory.segment_count.eq(1).all():
        raise ValueError('Cross-ticker source unsupported by this probe')
    return_bars = {r['ticker']: bars(r, prefix=True, allow_revised=revised_return_experiment).loc[lambda f: f.index < selection]
                   for r in inventory.to_dict('records')}
    universe = universe.loc[universe.ticker.map(lambda t: len(return_bars[t]) >= 252)].copy()
    if len(universe) != child['candidate_security_count']:
        raise ValueError('Prepared universe count differs from original child')
    incumbent = child['incumbent_weights']
    symbols = sorted(set(universe.ticker) | set(incumbent))
    prices = pd.concat([return_bars[t].Close.rename(t) for t in symbols], axis=1,
                       join='inner').dropna().tail(505)
    nav = bars(child['inputs']['target_nav'], prefix=True).Close.reindex(prices.index).ffill()
    prices = prices.loc[nav.notna()]
    nav = nav.loc[nav.notna()]
    returns = prices.pct_change(fill_method=None).dropna()
    target = nav.pct_change(fill_method=None).reindex(returns.index)
    if len(returns) != child['training_return_rows'] or str(returns.index[-1].date()) != child['training_end']:
        raise ValueError('Historical training calendar mismatch')
    execution_manifest = json.loads(read(child['inputs']['execution_price_manifest']))
    execution = frame(execution_manifest['artifacts']['inventory']).set_index('ticker')
    nominal = {}
    for ticker in universe.ticker:
        row = execution.loc[ticker].to_dict()
        if row['status'] != 'FETCHED':
            raise ValueError('Execution price not fetched')
        sidecar = json.loads(read(dict(path=row['sidecar_path'], sha256=row['sidecar_sha256'])))
        if sidecar['content_sha256'] != row['sha256']:
            raise ValueError('Execution sidecar mismatch')
        nominal[ticker] = bars(row).Close.reindex(prices.index)
    nominal = pd.DataFrame(nominal)
    if nominal.isna().any().any():
        raise ValueError('Nominal price calendar missing')
    universe = universe[['ticker', 'security_id', 'issuer_id', 'risk_chain']].copy()
    universe['synthetic_price'] = universe.ticker.map(lambda t: return_bars[t].Close.iloc[-1])
    universe['median_dollar_volume_usd'] = universe.ticker.map(
        lambda t: (return_bars[t].Close * return_bars[t].Volume).tail(63).median())
    spec_raw = (ROOT / 'config/ndx_cardinality_discovery_v1.yaml').read_bytes()
    smoke = yaml.safe_load(spec_raw)['synthetic_smoke_contract']
    contract = {k: smoke[k] for k in ('max_single_weight', 'min_single_weight', 'top_weight_cap',
        'minimum_effective_n_ratio', 'risk_chain_top1_cap', 'turnover_anchor_strength',
        'portfolio_cash_usd', 'minimum_cash_buffer_usd', 'minimum_median_dollar_volume_usd')}
    contract.update(shrinkage_intensity=smoke['fixed_shrinkage_intensity'],
                    window_days=126, fit_days=126, step_days=21, transaction_cost_bps=10.)
    old = frame(child['artifacts']['candidates'])
    full_candidates = old.copy(deep=True)
    old = old.sort_values(['tickers', 'weight_spec'])
    if not include_weight_controls:
        old = old.loc[old.weight_spec.eq('equal_weight')]
    if not all_equal_controls:
        old = old.head(1)
    controls = []
    for previous_row in old.to_dict('records'):
        new = evaluate_synthetic_portfolio(tuple(previous_row['tickers'].split(';')), universe, returns,
            target, list(incumbent), weight_spec=previous_row['weight_spec'], incumbent_weights=incumbent,
            execution_prices=nominal, **contract)
        equal, differences = [], {}
        for key in sorted(set(previous_row) & set(new)):
            if isinstance(new[key], (int, float)) and not isinstance(new[key], bool):
                actual, previous = float(new[key]), float(previous_row[key])
                if math.isclose(actual, previous, rel_tol=1e-10, abs_tol=1e-10):
                    equal.append(key)
                else:
                    differences[key] = dict(old=previous, current=actual)
        controls.append(dict(tickers=previous_row['tickers'], weight_spec=previous_row['weight_spec'], matched_numeric_field_count=len(equal),
                             numeric_differences=differences))
    for item in evidence:
        if hashlib.sha256(Path(item['path']).read_bytes()).hexdigest() != item['observed_sha256']:
            raise ValueError('Input changed during probe: ' + item['path'])
    if source_hashes != {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in source_paths}:
        raise ValueError('Probe numerical source/spec changed during execution')
    if screen_path.read_bytes() != screen_raw or (child_path.parents[5] / 'manifest.json').read_bytes() != run_raw:
        raise ValueError('Probe source root changed')
    report = dict(status='NEW_EVALUATOR_SINGLE_COORDINATE_OVERLAP_NOT_HISTORICAL_SEMANTIC_PROOF',
        holding_count=holding_count, include_weight_controls=include_weight_controls,
        numeric_fields_compared=sorted(set(equal) | set(differences)),
        revised_return_experiment=revised_return_experiment,
        numerical_sources=source_hashes, all_equal_controls=all_equal_controls,
        screen_sha256=hashlib.sha256(screen_raw).hexdigest(),
        observed_run_sha256=hashlib.sha256(run_raw).hexdigest(),
        current_spec_sha256=hashlib.sha256(spec_raw).hexdigest(),
        current_evaluator_sha256=hashlib.sha256((ROOT/'backtest/ndx_cardinality_discovery.py').read_bytes()).hexdigest(),
        identity_audit_rows=len(identity), training_rows=len(returns), controls=controls,
        contract=contract,
        evidence=evidence, promotion_allowed=False, source_equivalence_proven=False)
    if return_prepared:
        return report, dict(universe=universe, returns=returns, target_returns=target,
                            nominal_prices=nominal.reindex(returns.index),
                            incumbent_weights=incumbent, contract=contract), full_candidates, coordinate
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--revised-return-experiment', action='store_true',
                        help='Explicit new experiment with current revised return files; never old-source proof')
    parser.add_argument('--all-equal-controls', action='store_true', help='Evaluate all original equal-weight controls at this one k1 coordinate')
    parser.add_argument('--holding-count', type=int, default=1)
    parser.add_argument('--include-weight-controls', action='store_true', help='Also compare old non-equal weight rows')
    args = parser.parse_args()
    print(json.dumps(run(revised_return_experiment=args.revised_return_experiment,
                         all_equal_controls=args.all_equal_controls, holding_count=args.holding_count,
                         include_weight_controls=args.include_weight_controls), ensure_ascii=False, indent=2))
