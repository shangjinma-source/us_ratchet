"""Build an explicit, non-executable annual V4-shaped draft; never run search."""
import argparse
import gzip
import hashlib
import json
import sys
from copy import deepcopy
from datetime import datetime
from fractions import Fraction
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backtest.annual_identity_history_eligibility import assess_eligibility
BASE = 'tmp/conditional_calendar_year_inputs_20261016_v2'
ORDINARY = 'tmp/sndk_ordinary_annual_eligibility_20261016_v1'
SIMPLE = 'tmp/annual_simple_split_coordinates_20261016_v2/coordinates.json'
COMPLEX = 'tmp/annual_hon_cmcsa_coordinates_20261016_v1/mapping_candidate.json'
WDC = 'tmp/wdc_sndk_distribution_evidence_20261016_v1/conditional_assembly_v1.json'
PRIOR = 'tmp/next12_execution_prepare_20261014_v3/prepared.json'
BASIS = 'CONDITIONAL_RESTORED_HISTORICAL_NOMINAL_NOT_CERTIFIED'


def prepare(output):
    directory = (ROOT / output).resolve()
    if not directory.is_relative_to(ROOT / 'tmp') or directory.exists():
        raise ValueError('NEW_TMP_OUTPUT_REQUIRED')
    pins = {}

    def read(path, expected=None):
        path = Path(path).as_posix()
        raw = (ROOT / path).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if expected is not None and digest != expected:
            raise ValueError('SOURCE_DRIFT:' + path)
        if path in pins and pins[path] != digest:
            raise ValueError('PIN_CONFLICT:' + path)
        pins[path] = digest
        return raw

    def document(path):
        value = json.loads(read(path))
        for name, digest in (value.get('source_hashes', {}) if isinstance(value, dict) else {}).items():
            read(name, digest)
        return value

    def raw_bars(path, ticker):
        raw = read(path)
        quote = json.loads(gzip.decompress(raw) if raw[:2] == b'\x1f\x8b' else raw,
                           parse_float=str)['chart']['result'][0]
        if quote['meta']['symbol'] != ticker or quote['meta']['currency'] != 'USD':
            raise ValueError('RAW_IDENTITY_MISMATCH')
        zone = ZoneInfo(quote['meta']['exchangeTimezoneName'])
        return {datetime.fromtimestamp(ts, zone).date().isoformat():
                {field: quote['indicators']['quote'][0][field][index]
                 for field in ('open', 'high', 'low', 'close')}
                for index, ts in enumerate(quote['timestamp'])}

    manifest = document(BASE + '/source_manifest.json')
    simple = document(SIMPLE)
    complex_doc = document(COMPLEX)
    wdc_component = document(WDC)
    if wdc_component.get('conditional_model') is not True:
        raise ValueError('EXPLICIT_WDC_CONDITIONAL_SCOPE_REQUIRED')
    for path, digest in wdc_component['implementation_hashes'].items():
        read(path, digest)
    document('tmp/wdc_sndk_conditional_root_readback_20261016_v1.json')
    document('tmp/wdc_sndk_distribution_evidence_20261016_v1/channel_conditional_admission_proposal.json')
    identity = document('tmp/annual_identity_conditional_classification_20261016_v1.json')
    document(ORDINARY + '/revision_summary.json')
    prior = document(PRIOR)
    sources = {row['ticker']: row for row in manifest['sources']}
    history_closes = {ticker: {day: bar['close'] for day, bar in raw_bars(row['path'], ticker).items()}
                      for ticker, row in sources.items()}
    simple_rows = {row['ticker']: row for row in simple['rows']}
    complex_rows = {row['ticker']: row for row in complex_doc['rows']}
    eligibility = {}
    sessions = ['2023-12-29']
    for year in (2024, 2025, 2026):
        sessions += document(f'{BASE}/{year}_calendar.json')['sessions']
        for row in document(f'{ORDINARY}/{year}_eligibility.json'):
            eligibility[row['signal_date']] = row
    if sessions != sorted(set(sessions)):
        raise ValueError('INVALID_CONTINUOUS_CALENDAR')
    full_calendar = sorted(raw_bars('data/cache/research/current_raw_capture_20261014_v1/QQQ.response.bin', 'QQQ'))
    decisions = [day for index, day in enumerate(sessions[:-1])
                 if index == 0 or day[:7] != sessions[index + 1][:7]]
    metadata, ohlc, provenance, split_events = {}, {}, {}, []
    coordinates = {}
    for ticker, source in sources.items():
        if ticker == 'TRI':
            # No provider marks masquerade as corrected legal-action coordinates.
            coordinates[ticker] = None
        elif ticker in complex_rows:
            coordinates[ticker] = {day: dict(ohlc=row['nominal_ohlc'],
                training=row['training_capture_unit_close']) for day, row in complex_rows[ticker]['rows'].items()}
        elif ticker in ('WDC', 'SNDK'):
            coordinates[ticker] = {day: dict(ohlc=values, training=values['close'])
                for day, values in wdc_component['ohlc'][source['current_security_id']].items()}
        else:
            row = simple_rows[ticker]
            if row['nominal_ohlc'] is None:
                raise ValueError('UNHANDLED_BLOCKED_COORDINATE:' + ticker)
            coordinates[ticker] = {day: dict(ohlc=values['ohlc'],
                training=row['capture_unit_split_neutral_close'][day])
                for day, values in row['nominal_ohlc'].items()}
            if source['current_security_id']:
                for event in row['events']:
                    if sessions[0] < event['date'] <= sessions[-1]:
                        ratio = Fraction(event['ratio'])
                        split_events.append(dict(security_id=source['current_security_id'], date=event['date'],
                            new_shares=ratio.numerator, old_shares=ratio.denominator,
                            source_references=[SIMPLE]))
        sid = source['current_security_id']
        if sid is None:
            continue  # Remains in every candidate row with explicit history exclusion.
        ids = ['security:0000773840:438516106', 'security:0000773840:438516205'] if ticker == 'HON' else [sid]
        for mapped_sid in ids:
            metadata[mapped_sid] = dict(ticker=ticker, issuer_id=source['issuer_id'])
            ohlc[mapped_sid] = {}
            for day in sessions:
                if ticker == 'HON' and ((mapped_sid.endswith('106') and day >= '2026-06-29') or
                                        (mapped_sid.endswith('205') and day < '2026-06-29')):
                    continue
                if ticker == 'SNDK' and day < '2025-02-24':
                    continue
                if coordinates[ticker] is not None and day in coordinates[ticker]:
                    ohlc[mapped_sid][day] = coordinates[ticker][day]['ohlc']
            provenance[mapped_sid] = dict(whole_source=source['path'], price_basis=BASIS,
                conditional_annual_extension=True, external_identity_certified=False)
            if ticker in ('WDC', 'SNDK'):
                provenance[mapped_sid] = deepcopy(wdc_component['source_provenance'][mapped_sid])
    # Existing child marks value nontradable rights; they never assert delivery.
    for name, child in prior['child_instruments'].items():
        sid = child['security_id']
        metadata[sid] = dict(ticker=name, issuer_id=child['issuer_id'])
        bars = raw_bars(child['whole_ohlc_source'], name)
        ohlc[sid] = {day: bars[day] for day in sessions if day >= child['regular_way_start'] and day in bars}
        provenance[sid] = dict(whole_source=child['whole_ohlc_source'], price_basis=BASIS,
                              conditional_annual_extension=True, valuation_only=True, delivery_confirmed=False)
    windows = []
    for decision in decisions:
        guard = eligibility[decision]
        end = full_calendar.index(decision)
        training_days = full_calendar[end - 252:end + 1]
        if len(training_days) != 253 or training_days[0] != guard['training_start']:
            raise ValueError('TRAINING_CALENDAR_MISMATCH')
        ready = set(guard['price_history_ready'])
        candidates, prices, scenario_rows, search_metadata = [], {}, [], {}
        for ticker in manifest['universe']:
            source = sources[ticker]
            sid = source['current_security_id']
            if ticker == 'HON':
                sid = 'security:0000773840:' + ('438516106' if decision < '2026-06-29' else '438516205')
            row = dict(ticker=ticker, security_id=sid, issuer_id=source['issuer_id'],
                       training_source=source['path'])
            ordinary_start = ('2025-02-24' if ticker == 'SNDK' else
                              prior['child_instruments']['HONA']['regular_way_start']
                              if ticker == 'HONA' else source['first'])
            binding = dict(ticker=ticker, security_id=sid, role='SELECTION',
                mode='DECLARED_CONDITIONAL_LINK', valid_from=ordinary_start,
                valid_through='2026-10-13', known_asof='2026-10-16',
                source_references=[BASE + '/source_manifest.json', source['path']],
                assumption='Retrospective current observed universe; available whole-source series treated as ordinary selection history from first observation, not proven listing date or PIT. HON training continuity spans dated old/new share identity under stated coordinate mapping.')
            if ticker == 'SNDK':
                binding['source_references'].append(ORDINARY + '/revision_summary.json')
            if ticker == 'HONA':
                binding['source_references'] += [PRIOR] + prior['child_instruments']['HONA']['identity_source_references']
            identity_binding = dict(binding, regular_way_start=ordinary_start)
            channel_binding = dict(binding, channel='ORDINARY_REGULAR_WAY', currency='USD', source_id=source['path'])
            row['identity_binding'] = identity_binding
            row['channel_binding'] = channel_binding
            row['identity_history_guard'] = assess_eligibility(ticker=ticker, security_id=sid,
                decision_date=decision, regular_way_start=ordinary_start, sessions=full_calendar,
                closes=history_closes[ticker], identity_binding=identity_binding, channel_binding=channel_binding)
            if ticker not in ready:
                row.update(status='EXCLUDED_INSUFFICIENT_253_HISTORY',
                    history_exclusion=next(item for item in guard['excluded'] if item['ticker'] == ticker))
            elif ticker == 'TRI':
                row.update(status='BLOCKED_UNRESOLVED_COMPLEX_COORDINATES', training_close=None,
                           decision_cost=None, blockers=['TRI_2023_AND_2026_CAPITAL_IDENTITY_ACTION_UNRESOLVED'])
                prices[sid] = None
                search_metadata[sid] = metadata[sid]
                scenario_rows.append((sid, [None] * 12))
            else:
                if sid is None:
                    raise ValueError('HISTORY_READY_WITHOUT_IDENTITY:' + ticker)
                if row['identity_history_guard']['reasons']:
                    raise ValueError('GUARD_DISAGREES_WITH_READY_HISTORY:' + ticker + ':' + decision)
                values = [coordinates[ticker][day]['training'] for day in training_days]
                cost = coordinates[ticker][decision]['ohlc']['close']
                gross = [str(Fraction(values[index + 21]) / Fraction(values[index])) for index in range(0, 252, 21)]
                row.update(status='DRAFT_CONDITIONAL_INPUT_COMPUTED', training_close=values,
                           decision_cost=cost, training_gross=gross)
                prices[sid], search_metadata[sid] = cost, metadata[sid]
                scenario_rows.append((sid, gross))
            candidates.append(row)
        args = dict(prices=prices, metadata=search_metadata, entered_cash='20000', fee_bps='0',
            minimum_cash_buffer='0', training_scenarios=[{sid: gross[index] for sid, gross in scenario_rows}
                                                       for index in range(12)],
            scenario_dates=training_days[21::21], decision_date=decision,
            max_objective_evaluations=8192, fixed_seed='fresh-quantity-20261014-v1')
        windows.append(dict(decision_date=decision, decision_cutoff=decision,
            active_date=sessions[sessions.index(decision) + 1], training_dates=training_days,
            candidates=candidates, member_denominator=101, search_arguments=args,
            status='BLOCKED_NOT_EXECUTABLE_TRI_NULL_INPUT_RETAINED'))
    events = deepcopy(prior['distribution_events']) + deepcopy(wdc_component['distribution_events'])
    read(Path(__file__).relative_to(ROOT).as_posix())
    read('backtest/annual_identity_history_eligibility.py')
    read('backtest/annual_simple_split_coordinates.py')
    for path, digest in list(pins.items()):
        read(path, digest)
    result = dict(schema='ANNUAL_CONTINUOUS_V4_SHAPED_DRAFT_V1', status='BLOCKED_NOT_EXECUTABLE',
        execution_admitted=False, session_dates=sessions, windows=windows, metadata=metadata,
        ohlc=ohlc, source_provenance=provenance, split_events_reference_only=split_events,
        identity_migrations=[], cash_stock_merger_events=[], fractional_settlements={},
        distribution_events=events, distribution_fractional_cash_values={},
        unsupported_conversions=[], supported_conversions=[], account_model=prior['account_model'],
        source_hashes=pins, initial_cash='20000', initial_shares={}, fee_bps='0',
        minimum_cash_buffer='0', price_only=True, point_in_time_certified=False,
        full_observed_domain=manifest['universe'], identity_assumptions=identity['rows'],
        material_blockers=['TRI null prices/scenarios intentionally retained in every history-ready domain',
            'Annual conditional source/action extension and history guard review pending'],
        wdc_conditional_model=True, child_delivery_verified=False,
        continuous_account=True, yearly_capital_reset=False, economic_calls=0,
        no_silent_domain_filter=True, no_generated_fake_price=True)
    directory.mkdir()
    (directory / 'draft_prepared.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    preflight = dict(status='DRAFT_STRUCTURAL_PREFLIGHT_ONLY_NOT_V4_EXECUTABLE',
        sessions=len(sessions), windows=len(windows), full_domain_per_window=101,
        decision_dates=decisions, missing_coordinate_security='TRI',
        v4_assembler_invoked=False, economic_calls=0, blockers=result['material_blockers'])
    (directory / 'preflight.json').write_text(json.dumps(preflight, indent=2), encoding='utf-8')
    print(json.dumps(preflight))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    prepare(parser.parse_args().output)
