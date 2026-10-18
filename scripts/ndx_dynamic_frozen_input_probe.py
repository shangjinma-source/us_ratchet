"""Restore sealed dynamic schedules for new execution research, never reselect.

The captured common calendar is a historical diagnostic calendar, not a new
independently verified complete market/PIT universe. No economic replay here.
"""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backtest import ndx_dynamic_repair_research_bundle as bundle

CAPTURE_SHA = 'c078e04146dd9e834aa4f4c57dfe8bfdbed87970e020507893a0bb98e42d4737'
SOURCE = Path(__file__).resolve()
_LOADED = {str(ROOT/path): hashlib.sha256((ROOT/path).read_bytes()).hexdigest()
           for path in bundle.CODE_FILES}
_LOADED[str(SOURCE)] = hashlib.sha256(SOURCE.read_bytes()).hexdigest()


def _check_sources(sources):
    if any(hashlib.sha256(Path(path).read_bytes()).hexdigest() != digest
           for path, digest in sources.items()):
        raise ValueError('Dynamic input source changed since import/capture')


def prepare_lane(lane_key):
    if type(lane_key) is not str or not lane_key or lane_key != lane_key.strip():
        raise ValueError('Explicit exact lane key required')
    _check_sources(_LOADED)
    path = ROOT/bundle.OUTPUT_RELATIVE/CAPTURE_SHA/'capture.json'
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != CAPTURE_SHA:
        raise ValueError('Sealed dynamic capture identity differs')
    captured = json.loads(raw)
    if (bundle.json_bytes(captured) != raw or set(captured) != bundle.CAPTURE_FIELDS
            or captured['version'] != bundle.VERSION
            or captured['code_hashes'] != bundle.code_hashes(ROOT)):
        raise ValueError('Dynamic capture schema/code binding differs')
    archive = bundle.CapturedSources(captured['sources'])
    manifest, opens, closes, lanes = bundle.derive_inputs(ROOT, archive, captured['tickers'])
    if captured['selected_provenance_counts'] != {key: len(value['schedule']) for key, value in lanes.items()}:
        raise ValueError('Dynamic lane denominator differs')
    if lane_key not in lanes:
        raise ValueError('Requested lane absent from sealed capture')
    lane = lanes[lane_key]
    start = lane['schedule'][0]['decision_date']
    calendar = closes.loc[start:manifest['valuation_end']].index
    if len(calendar) < 2 or not opens.loc[calendar].index.equals(calendar):
        raise ValueError('Insufficient dynamic decision/fill calendar')
    for row in lane['schedule']:
        if row['decision_date'] not in calendar or row['execution_date'] not in calendar:
            raise ValueError('Dynamic decision/fill missing from captured calendar')
        if calendar.get_loc(row['execution_date']) != calendar.get_loc(row['decision_date'])+1:
            raise ValueError('Dynamic fill must be next captured session')
    tickers = sorted({value['ticker'] for row in lane['schedule'] for value in row['targets'].values()})
    identities = {}
    issuer_identities = {}
    for row in lane['schedule']:
        for identity, target in row['targets'].items():
            identities.setdefault(identity, set()).add(target['ticker'])
            issuer_identities.setdefault(identity, set()).add(target['issuer_id'])
    if any(len(values) != 1 for values in issuer_identities.values()):
        raise ValueError('Captured security changes issuer')
    observed = {**_LOADED, str(path): CAPTURE_SHA}
    _check_sources(observed)
    summary = dict(lane_key=lane_key, capture_sha256=CAPTURE_SHA,
        date_start=str(calendar[0].date()), date_end=str(calendar[-1].date()),
        session_count=len(calendar), decision_count=len(lane['schedule']),
        k_path=[len(row['targets']) for row in lane['schedule']],
        tickers=tickers, captured_lane_count=len(lanes),
        aliases_by_security={key: sorted(values) for key, values in identities.items() if len(values)>1},
        capital_usd=25000., minimum_cash_buffer_usd=100., transaction_cost_bps=10.,
        contains_bkr='BKR' in tickers, portfolio_optimization=True,
        fixed_cardinality_claim=False, migration_control=False,
        source_scope='SEALED_DYNAMIC_DIAGNOSTIC_INPUT_NOT_RESELECTED_CURRENT_POOL',
        calendar_scope='CAPTURED_COMMON_CALENDAR_NOT_EXTERNALLY_AUTHENTICATED',
        full_pit_universe_verified=False, corporate_action_coverage_verified=False,
        source_hashes=observed, economic_replay_performed=False, promotion_allowed=False)
    return dict(summary=summary, schedule=lane['schedule'], risk_chains=lane['risk_chains'],
                opens=opens.loc[calendar, tickers].copy(), closes=closes.loc[calendar, tickers].copy(),
                captured_manifest=manifest)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lane-key', required=True)
    print(json.dumps(prepare_lane(parser.parse_args().lane_key)['summary'], indent=2))
