"""Frozen original-eight input attribution; never read today's holdings."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from scripts.ndx_dynamic_frozen_input_probe import prepare_lane, ROOT, CAPTURE_SHA, bundle, _check_sources
from backtest.ndx_incumbent_risk_overlay_research import load_incumbent_risk_overlay


def prepare_control(lane_key):
    candidate = prepare_lane(lane_key)
    path = ROOT/bundle.OUTPUT_RELATIVE/CAPTURE_SHA/'capture.json'
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != CAPTURE_SHA:
        raise ValueError('Capture changed')
    captured = json.loads(raw)
    archive = bundle.CapturedSources(captured['sources'])
    manifest, index, _, _ = bundle.source_contract(ROOT, archive)
    batch, track, _ = lane_key.split('/')
    matches = index[(index.source_batch == batch) & (index.universe_track == track)
                    & (index.name == 'original_8_whole_lot_rebalances')]
    if len(matches) != 1:
        raise ValueError('Ambiguous control identity trace')
    descriptor = matches.iloc[0]
    records = bundle.csv(archive.read(descriptor.path, descriptor.sha256))
    weights = manifest['capital_replay_source_coverage']['original_8_incumbent_weights']
    targets = None
    for row in records.to_dict('records'):
        holdings, attributed = json.loads(row['holdings']), json.loads(row['target_weights'])
        if set(holdings) != set(attributed):
            raise ValueError('Control identity/weight coverage differs')
        current = {key: dict(ticker=value['ticker'], issuer_id=value['issuer_id'],
                            target_weight=attributed[key]) for key, value in holdings.items()}
        if {value['ticker']: value['target_weight'] for value in current.values()} != weights:
            raise ValueError('Original control weights changed')
        if targets is not None and current != targets:
            raise ValueError('Control identity changed within trace')
        targets = current
    if targets is None:
        raise ValueError('Empty original control trace')
    metadata = candidate['summary']
    risk = load_incumbent_risk_overlay(
        reviewed_manifest_path=ROOT/'data/cache/candidate_pools/ndx_taxonomy_v2/incumbent_overlay/reviewed/manifest.json',
        expected_manifest_sha256='8ab02a983a5b316b0da053d3f97dd87f87b863a36a4f359a5ab23b74700b384b',
        tickers=sorted(weights), date_start=metadata['date_start'], date_end=metadata['date_end'])
    opens, closes = bundle.captured_prices(manifest, archive, sorted(weights))
    calendar = candidate['closes'].index
    schedule = [dict(decision_date=row['decision_date'], execution_date=row['execution_date'],
                     targets=deepcopy(targets)) for row in candidate['schedule']]
    labels = {key: risk['risk_chain_by_ticker'][value['ticker']] for key, value in targets.items()}
    own = Path(__file__).resolve()
    sources = {**metadata['source_hashes'], **risk['provenance']['source_hashes'],
               str(own): hashlib.sha256(own.read_bytes()).hexdigest()}
    _check_sources(sources)
    return dict(schedule=schedule, opens=opens.loc[calendar].copy(), closes=closes.loc[calendar].copy(),
                risk_chains={row['decision_date']: dict(labels) for row in schedule},
                original_weights=weights, source_hashes=sources,
                identity_scope='SEALED_EXECUTION_ATTRIBUTION_NOT_EXTERNAL_IDENTITY_PROOF',
                risk_provenance=risk['provenance'], capital_usd=metadata['capital_usd'],
                minimum_cash_buffer_usd=metadata['minimum_cash_buffer_usd'],
                transaction_cost_bps=metadata['transaction_cost_bps'], date_end=metadata['date_end'])
