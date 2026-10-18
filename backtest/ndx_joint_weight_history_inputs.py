"""Prepare byte-bound historical panels without reading live account state.

The ancestor run is a locally observed lineage root, not external authenticity.
An explicit revised-return experiment never revises NAV, identity, or execution
sources, and never silently removes a member of the historical candidate pool.
"""
import hashlib
import csv
import io
import json
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from backtest.ndx_cardinality_capital_replay_summary import _exact_historical_csv_prefix
from backtest.ndx_joint_weight_evaluation import CONTRACT_FIELDS
from data.ndx_security_identity import _validated_intervals


def _require(value, message):
    if not value:
        raise ValueError(message)


def _positive_integer(value, label):
    _require(isinstance(value, (int, np.integer)) and not isinstance(value, (bool, np.bool_))
             and value > 0, 'Invalid integer: ' + label)
    return int(value)


def _boolean_mask(values, label):
    _require(values.map(lambda value: isinstance(value, (bool, np.bool_))).all(),
             'Nonboolean eligibility: ' + label)
    return values.eq(True)


def _validate_nominal_sidecar(sidecar, ticker, expected_hash):
    _require(sidecar.get('content_sha256') == expected_hash
             and sidecar.get('dataset_key') == ticker
             and sidecar.get('price_basis') == 'unadjusted_nominal_trade_price'
             and sidecar.get('whole_lot_execution_use_only') is True
             and sidecar.get('return_usage_allowed') is False, 'Nominal sidecar semantics mismatch')


class _Sources:
    def __init__(self):
        self.evidence = []
        self.observed = {}

    def observe(self, path, raw):
        path = Path(path).resolve()
        digest = hashlib.sha256(raw).hexdigest()
        _require(path not in self.observed or self.observed[path] == digest,
                 'Source changed during preparation: ' + str(path))
        self.observed[path] = digest

    def validate_unchanged(self):
        for path, digest in self.observed.items():
            _require(hashlib.sha256(path.read_bytes()).hexdigest() == digest,
                     'Source changed during preparation: ' + str(path))

    def read(self, descriptor, *, prefix=False, revised=False):
        path = Path(descriptor['path'])
        _require(path.is_absolute(), 'Source path must be absolute')
        raw = path.read_bytes()
        self.observe(path, raw)
        observed = hashlib.sha256(raw).hexdigest()
        expected = descriptor['sha256']
        _require(isinstance(expected, str) and len(expected) == 64
                 and all(v in '0123456789abcdef' for v in expected), 'Invalid source digest')
        status = 'EXACT'
        if observed != expected:
            recovered = _exact_historical_csv_prefix(raw, expected, str(path)) if prefix else None
            if recovered is not None:
                raw, status = recovered, 'EXACT_PREFIX'
            elif revised:
                status = 'REVISED_RETURN_DATA_NEW_EXPERIMENT'
            else:
                raise ValueError('Unrecoverable source: ' + str(path))
        self.evidence.append(dict(path=str(path), expected_sha256=expected,
            observed_sha256=observed, used_sha256=hashlib.sha256(raw).hexdigest(), status=status))
        return raw

    def csv(self, descriptor, **options):
        raw = self.read(descriptor, **options)
        header = next(csv.reader(io.StringIO(raw.decode('utf-8-sig'))))
        _require(len(header) == len(set(header)), 'Duplicate source columns')
        frame = pd.read_csv(io.BytesIO(raw), keep_default_na=False)
        _require(not frame.columns.duplicated().any(), 'Duplicate source columns')
        return frame

    def bars(self, descriptor, **options):
        frame = self.csv(descriptor, **options)
        _require({'Date', 'Close'}.issubset(frame), 'Incomplete price data')
        frame['Date'] = pd.to_datetime(frame.Date, errors='raise')
        index = pd.DatetimeIndex(frame.Date)
        _require(not index.hasnans and index.tz is None and index.is_unique
                 and index.is_monotonic_increasing and index.equals(index.normalize()),
                 'Invalid bar dates')
        for key in ('Close', 'Volume'):
            if key in frame:
                _require(not frame[key].map(lambda v: isinstance(v, (bool, np.bool_))).any(),
                         'Boolean price data')
                frame[key] = pd.to_numeric(frame[key], errors='raise')
                _require(np.isfinite(frame[key]).all() and (frame[key] >= 0).all(), 'Invalid bar values')
        _require((frame.Close > 0).all(), 'Nonpositive prices')
        return frame.set_index('Date')


def _rules(raw):
    payload = yaml.safe_load(raw)
    _require(payload.get('schema_version') == 1, 'Unsupported lifecycle schema')
    result = {}
    for rule in payload['rules']:
        original_cik = rule['cik']
        _require(not isinstance(original_cik, bool) and isinstance(original_cik, (int, str)),
                 'Invalid lifecycle CIK type')
        cik = str(original_cik).zfill(10)
        _require(cik.isdigit() and len(cik) == 10 and int(cik) > 0 and cik not in result,
                 'Duplicate/invalid lifecycle issuer')
        cusip = rule['cusip']
        _require(isinstance(cusip, str) and len(cusip) == 9 and cusip.isalnum()
                 and cusip == cusip.upper(), 'Invalid lifecycle CUSIP')
        _require(isinstance(rule['recognized_tickers'], list)
                 and all(isinstance(t, str) and t and t == t.strip().upper()
                         for t in rule['recognized_tickers']), 'Invalid recognized tickers')
        item = dict(rule)
        item['intervals'] = _validated_intervals(rule['rule_id'], rule['intervals'])
        _require(all(v.price_ticker in rule['recognized_tickers'] for v in item['intervals']),
                 'Unrecognized lifecycle ticker')
        result[cik] = item
    return result


def _rule_for(security, ticker, selection, rules):
    pieces = security.split(':')
    _require(len(pieces) == 3 and pieces[0] == 'security' and pieces[1].isdigit(),
             'Malformed security identity')
    rule = rules.get(pieces[1].zfill(10))
    if rule:
        _require(pieces[2] == rule['cusip'] and ticker in rule['recognized_tickers'],
                 'Lifecycle identity mismatch')
        _require([v.price_ticker for v in rule['intervals'] if v.contains(selection)] == [ticker],
                 'Ticker invalid at selection')
    return rule


def _stitch(parts, rule, selection):
    segments = []
    for ticker, bars in parts:
        mask = bars.index < selection
        if rule:
            intervals = [v for v in rule['intervals'] if v.price_ticker == ticker]
            _require(bool(intervals), 'Unrecognized segment ticker')
            valid = np.zeros(len(bars), dtype=bool)
            for interval in intervals:
                valid |= ((bars.index >= interval.effective_from) if interval.effective_from is not None else True) & (
                    (bars.index <= interval.effective_to) if interval.effective_to is not None else True)
            mask &= valid
        segment = bars.loc[mask]
        _require(not segment.empty, 'Empty required lifecycle segment')
        segments.append(segment)
    result = pd.concat(segments).sort_index(kind='stable')
    _require(result.index.is_unique, 'Overlapping lifecycle price dates')
    return result


def prepare_joint_weight_history_inputs(child_manifest_path, expected_sha256, *,
        evaluation_contract, training_lookback_days, minimum_price_rows_before_selection,
        allow_revised_return_data=False):
    """Return explicit panels and lineage evidence; performs no evaluations/writes.

    evaluation_contract is the caller's new experiment contract, not a claim
    that the old spec bytes were recovered. fit/window/step must be explicit.
    """
    _require(type(allow_revised_return_data) is bool, 'Explicit revised-data flag required')
    _require(set(evaluation_contract) == CONTRACT_FIELDS, 'Complete evaluation contract required')
    for key, value in evaluation_contract.items():
        _require(not isinstance(value, (bool, np.bool_)) and isinstance(value, (int, float))
                 and np.isfinite(value), 'Invalid contract number: ' + key)
    for value in (training_lookback_days, minimum_price_rows_before_selection,
                  evaluation_contract['fit_days'], evaluation_contract['window_days'], evaluation_contract['step_days']):
        _require(type(value) is int and value > 0, 'Explicit positive integer windows required')
    _require(evaluation_contract['transaction_cost_bps'] >= 0
             and evaluation_contract['minimum_median_dollar_volume_usd'] > 0,
             'Invalid evaluation costs/liquidity')
    _require(0 <= evaluation_contract['minimum_cash_buffer_usd'] < evaluation_contract['portfolio_cash_usd'],
             'Invalid evaluation capital')
    for key in ('shrinkage_intensity', 'turnover_anchor_strength'):
        _require(0 <= evaluation_contract[key] <= 1, 'Invalid evaluation fraction')
    for key in ('max_single_weight', 'min_single_weight', 'top_weight_cap',
                'minimum_effective_n_ratio', 'risk_chain_top1_cap'):
        _require(0 < evaluation_contract[key] <= 1, 'Invalid evaluation risk bound')
    _require(evaluation_contract['min_single_weight'] <= evaluation_contract['max_single_weight'],
             'Reversed evaluation weight bounds')
    sources = _Sources()
    source_root = Path(__file__).resolve().parents[1]
    preparation_sources = {}
    for relative in ('backtest/ndx_joint_weight_history_inputs.py',
                     'backtest/ndx_cardinality_capital_replay_summary.py',
                     'backtest/ndx_joint_weight_evaluation.py', 'data/ndx_security_identity.py'):
        code_path = source_root / relative
        code_raw = code_path.read_bytes()
        sources.observe(code_path, code_raw)
        preparation_sources[relative] = hashlib.sha256(code_raw).hexdigest()
    path = Path(child_manifest_path).resolve()
    child = json.loads(sources.read(dict(path=str(path), sha256=expected_sha256)))
    _require(child.get('promotion_allowed') is False and child.get('research_track') == 'portfolio_optimization',
             'Not a research child')
    for key in ('holding_count', 'candidate_security_count', 'candidate_issuer_count', 'training_return_rows'):
        _positive_integer(child[key], key)
    selection = pd.Timestamp(child['selection_date'])
    _require(not pd.isna(selection) and selection.tzinfo is None
             and selection == selection.normalize(), 'Invalid selection date')
    run_path = path.parents[5] / 'manifest.json'
    run_raw = run_path.read_bytes()
    sources.observe(run_path, run_raw)
    source_run = json.loads(run_raw)
    discovery = json.loads(sources.read(source_run['inputs']['discovery_manifest']))
    members = sources.csv(discovery['artifacts']['eligible_securities'])
    membership = sources.csv(child['inputs']['membership_audit'])
    identity = sources.csv(child['inputs']['identity_audit'])
    rules = _rules(sources.read(child['inputs']['security_lifecycle']))
    mask = lambda f: f.selection_date.eq(child['selection_date']) & f.universe_track.eq(child['universe_track'])
    coordinate = members.loc[mask(members) & _boolean_mask(members.membership_window_eligible, 'membership_window_eligible')]
    audit = membership.loc[mask(membership)]
    universe = coordinate.merge(audit.loc[_boolean_mask(audit.input_ready, 'input_ready'), ['security_id']],
                                on='security_id', validate='one_to_one')
    _require(not universe.empty and not universe.ticker.duplicated().any()
             and not universe.security_id.duplicated().any(), 'Invalid historical universe')
    blocked = set()
    for value in identity.loc[identity.identity_status.ne('IDENTITY_MATCH'), 'issuer_ids']:
        blocked.update(str(value).split(';'))
    _require(not set(universe.issuer_id) & blocked, 'Unresolved lifecycle identity')
    inventory = sources.csv(child['artifacts']['price_inventory'])
    _require(not inventory.ticker.duplicated().any(), 'Duplicate return inventory')
    incumbent = child['incumbent_weights']
    _require(incumbent and all(not isinstance(v, bool) and isinstance(v, (int, float))
        and np.isfinite(v) and v >= 0 for v in incumbent.values())
        and abs(sum(incumbent.values())-1) < 1e-10, 'Invalid explicit incumbent weights')
    _require(set(inventory.ticker) == set(universe.ticker) | set(incumbent), 'Return inventory coverage differs')
    by_ticker = universe.set_index('ticker')
    return_bars, ticker_rules = {}, {}
    for row in inventory.to_dict('records'):
        ticker = row['ticker']
        rule = _rule_for(str(by_ticker.loc[ticker, 'security_id']), ticker, selection, rules) if ticker in by_ticker.index else None
        ticker_rules[ticker] = rule
        names, paths, hashes = (str(row[k]).split(';') for k in ('source_tickers', 'path', 'sha256'))
        _require(len(names) == len(paths) == len(hashes) == _positive_integer(row['segment_count'], 'segment_count')
                 and len(names) == len(set(names)), 'Ambiguous source segments')
        _require((rule is not None or names == [ticker]), 'Cross-ticker source lacks identity rule')
        if rule:
            expected_names = [v.price_ticker for v in rule['intervals']
                              if v.effective_from is None or v.effective_from < selection]
            _require(names == expected_names and row['lifecycle_rule_id'] == rule['rule_id'], 'Lifecycle segments missing/misordered')
        parts = [(name, sources.bars(dict(path=p, sha256=h), prefix=True,
                    revised=allow_revised_return_data)) for name, p, h in zip(names, paths, hashes)]
        result = _stitch(parts, rule, selection)
        _require('Volume' in result and len(result) == _positive_integer(row['rows_before_selection'], 'rows_before_selection')
                 and str(result.index.min().date()) == row['data_start']
                 and str(result.index.max().date()) == row['data_end'], 'Historical return coverage changed')
        return_bars[ticker] = result
    excluded = {t for t in universe.ticker if len(return_bars[t]) < minimum_price_rows_before_selection}
    _require(excluded == set(child.get('excluded_for_history', [])), 'Historical exclusion set differs')
    universe = universe.loc[~universe.ticker.isin(excluded)].copy()
    _require(len(universe) == child['candidate_security_count']
             and universe.issuer_id.nunique() == child['candidate_issuer_count'], 'Historical pool changed')
    symbols = sorted(set(universe.ticker) | set(incumbent))
    prices = pd.concat([return_bars[t].Close.rename(t) for t in symbols], axis=1, join='inner').dropna().tail(training_lookback_days+1)
    nav = sources.bars(child['inputs']['target_nav'], prefix=True).Close.reindex(prices.index).ffill()
    prices, nav = prices.loc[nav.notna()], nav.loc[nav.notna()]
    returns = prices.pct_change(fill_method=None).dropna()
    target = nav.pct_change(fill_method=None).reindex(returns.index)
    _require(len(returns) == child['training_return_rows']
             and str(returns.index.max().date()) == child['training_end']
             and len(returns) >= evaluation_contract['fit_days'] + evaluation_contract['window_days']
             and np.isfinite(target).all(), 'Historical aligned training calendar mismatch')
    execution = json.loads(sources.read(child['inputs']['execution_price_manifest']))
    _require(execution.get('whole_lot_execution_use_only') is True
             and execution.get('status') == 'READY', 'Invalid nominal execution bundle')
    execution_inventory = sources.csv(execution['artifacts']['inventory'])
    _require(not execution_inventory.ticker.duplicated().any(), 'Duplicate nominal inventory')
    execution_inventory = execution_inventory.set_index('ticker')
    nominal = {}
    for ticker in universe.ticker:
        rule = ticker_rules[ticker]
        names = [v.price_ticker for v in rule['intervals'] if v.effective_from is None or v.effective_from < selection] if rule else [ticker]
        parts = []
        for name in names:
            row = execution_inventory.loc[name]
            _require(row['status'] == 'FETCHED', 'Missing nominal source')
            sidecar = json.loads(sources.read(dict(path=row['sidecar_path'], sha256=row['sidecar_sha256'])))
            _validate_nominal_sidecar(sidecar, name, row['sha256'])
            parts.append((name, sources.bars(row)))
        nominal[ticker] = _stitch(parts, rule, selection).Close.reindex(returns.index)
    nominal = pd.DataFrame(nominal)
    _require(np.isfinite(nominal).all().all(), 'Missing nominal calendar')
    universe = universe[['ticker', 'security_id', 'issuer_id', 'risk_chain']].copy()
    universe['synthetic_price'] = universe.ticker.map(lambda t: return_bars[t].Close.iloc[-1])
    universe['median_dollar_volume_usd'] = universe.ticker.map(lambda t: (return_bars[t].Close * return_bars[t].Volume).tail(63).median())
    sources.validate_unchanged()
    return dict(universe=universe, returns=returns, target_returns=target, nominal_prices=nominal,
        incumbent_weights=dict(incumbent), contract=dict(evaluation_contract),
        task_context=dict(selection_date=child['selection_date'], decision_data_end=child['training_end'],
                          universe_track=child['universe_track'], holding_count=child['holding_count']),
        provenance=dict(sources=sources.evidence, observed_run_sha256=hashlib.sha256(run_raw).hexdigest(),
            preparation_sources=preparation_sources,
            external_root_authentication=False, historical_spec=child['inputs'].get('spec'),
            historical_evaluator_contract=source_run.get('run_contract'),
            revised_return_data_used=any(v['status']=='REVISED_RETURN_DATA_NEW_EXPERIMENT' for v in sources.evidence),
            promotion_allowed=False))
