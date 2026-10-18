"""Offline four-security conditional inputs; no HTTP, fit, or execution."""
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
import gzip
import hashlib
from importlib.resources import files
from io import BytesIO
import json
import os
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backtest import ndx_root_price_archive_contract_research as archive

SOURCE = Path(__file__).resolve()
NY_SOURCE = Path(str(files('tzdata.zoneinfo.America').joinpath('New_York'))).resolve()
NY_BYTES = NY_SOURCE.read_bytes()
NY = ZoneInfo.from_file(BytesIO(NY_BYTES), key='America/New_York')
BASE = ROOT / 'data/cache/research'
OUTPUT = BASE / 'drawdown_four_input_assembly_20260923_v1/assembly.json'
BOUND = {
    'parent': ('bad_tail_five_input_projection_20260923_v1/projection.json', '77d03b11751322158158b66a18ecf19fd669cacfa730b99c3dbda1139b25e6be'),
    'identity': ('seven_dated_identity_assembly_20260919_v1/identities.json', 'ed810b2fc1626e05f3c1edee10212645dad37435461b8b7e8d01dcba1354e7c2'),
    'benchmark': ('return_six_period_benchmarks_20260923_v1/benchmarks.json', 'ef7ccdbe45a95fdf616d1b681bf9cd5c431db01585d30cf979e5cd4f2d45b423'),
    'lane': ('cutoff_training_lanes_20260923_v2/prepare.json', 'b7eaff190f3b2225db87d14fd0f7afc0cd9420536e9a4661f986f8ac319a96ba'),
    'raw': ('legacy_pool_remaining_split_probe_20260912_v1/ENPH.response.bin', '9674ec83b89380b9f22fccb864d5e61bb3b9f270ee93b69a0b75f2250054c45f'),
    'metadata': ('legacy_pool_remaining_split_probe_20260912_v1/ENPH.metadata.json', 'e0b7eb2e6e26b63f51f7ccc675217b87b41dd5e60d25313aa37322eb8adff0ce'),
}
LOADED = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in
          (SOURCE, archive.SOURCE, Path(archive.drift.__file__).resolve())}
LOADED[str(NY_SOURCE)] = hashlib.sha256(NY_BYTES).hexdigest()
CLOCK = [('2023-03-31', '2023-04-03'), ('2023-04-28', '2023-05-01'),
         ('2023-05-31', '2023-06-01'), ('2023-06-30', '2023-07-03'),
         ('2023-07-31', '2023-08-01'), ('2023-08-31', '2023-09-01')]
COORDINATES = {'BKR': ('0001701605', '05722G100', 'energy_technology'),
               'CDNS': ('0000813672', '127387108', 'eda_ip'),
               'ENPH': ('0001463101', '29355A107', 'energy_technology'),
               'FTNT': ('0001262039', '34959E109', 'cybersecurity')}
ENPH_URL = 'https://query1.finance.yahoo.com/v8/finance/chart/ENPH?period1=1640995200&period2=1789155251&interval=1d&events=div%2Csplits'
FALSE = ('new_http_performed', 'fit_performed', 'execution_performed', 'orders_generated',
         'execution_risk_chain_union_verified', 'target_schedule_built', 'target_schedule_validity_verified',
         'provider_binding_verified', 'continuous_identity_interval_verified', 'historical_membership_verified',
         'exchange_calendar_completeness_verified', 'quote_basis_independently_authenticated',
         'corporate_action_completeness_verified', 'dividend_cash_flows_modelled',
         'historical_full_source_closure_verified', 'point_in_time_verified', 'promotion_allowed')


def require(value, message):
    if not value:
        raise ValueError(message)


def unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'Duplicate JSON key')
        result[key] = value
    return result


def reference(role):
    path, digest = BOUND[role]
    return dict(path=str(BASE / path), sha256=digest)


def decimal_string(value):
    require(type(value) in (Decimal, int, str), 'Exact numeric token required')
    number = Decimal(value)
    require(number.is_finite() and number > 0, 'Positive finite price required')
    return str(number)


def decode_enph(raw, metadata, calendar):
    archive.strict(LOADED)
    require(len(calendar) == 107 and calendar == sorted(set(calendar)) and
            (calendar[0], calendar[-1]) == ('2023-03-31', '2023-09-01'), 'Exact 107-session ENPH window required')
    require(hashlib.sha256(raw).hexdigest() == metadata['response_sha256'] and
            len(raw) == metadata['response_bytes'] and metadata['response_path'] == reference('raw')['path'],
            'Transport receipt differs')
    require(metadata['http_status'] == 200 and metadata['transport_success'] is True and
            metadata['request']['method'] == 'GET' and metadata['request']['credentials_sent'] is False,
            'Successful public GET receipt required')
    require(metadata['request']['url'] == metadata['final_url'] == ENPH_URL, 'Original ENPH request URL differs')
    started, received = [datetime.fromisoformat(metadata[k]) for k in ('started_at_utc', 'received_at_utc')]
    require(all(x.tzinfo is not None and x.utcoffset().total_seconds() == 0 for x in (started, received)) and
            started <= received, 'Aware UTC receipt clocks required')
    decoded = gzip.decompress(raw) if raw[:2] == b'\x1f\x8b' else raw
    chart = json.loads(decoded, parse_float=Decimal, object_pairs_hook=unique)['chart']
    require(chart['error'] is None and len(chart['result']) == 1, 'Unique successful chart required')
    result = chart['result'][0]
    require(result['meta']['symbol'] == 'ENPH' and result['meta']['currency'] == 'USD' and
            result['meta']['exchangeTimezoneName'] == 'America/New_York' and
            result['meta']['instrumentType'] == 'EQUITY' and result['meta']['dataGranularity'] == '1d',
            'ENPH USD NY daily equity required')
    require(result.get('events', {}) == {}, 'Unexpected events require separate adjudication')
    timestamps = result['timestamp']
    require(all(type(t) is int for t in timestamps) and timestamps == sorted(set(timestamps)), 'Unique ordered timestamps required')
    dates = [datetime.fromtimestamp(t, timezone.utc).astimezone(NY).date().isoformat() for t in timestamps]
    require(len(dates) == len(set(dates)), 'Duplicate NY session')
    quotes = result['indicators']['quote']
    require(len(quotes) == 1, 'Unique quote series required')
    quote = quotes[0]
    require(all(len(quote[k]) == len(timestamps) for k in ('open', 'close')), 'Quote length differs')
    indices = [i for i, day in enumerate(dates) if calendar[0] <= day <= calendar[-1]]
    require([dates[i] for i in indices] == calendar, 'ENPH window differs from exact benchmark calendar')
    rows = [dict(session=dates[i], timestamp_utc=timestamps[i],
                 open=decimal_string(quote['open'][i]), close=decimal_string(quote['close'][i])) for i in indices]
    return dict(ticker='ENPH', rows=rows, raw_reference=reference('raw'), metadata_reference=reference('metadata'),
                transport_sha256=hashlib.sha256(raw).hexdigest(), decoded_sha256=hashlib.sha256(decoded).hexdigest(),
                transport_encoding='gzip' if decoded is not raw else 'identity', received_at_utc=metadata['received_at_utc'],
                request=deepcopy(metadata['request']), currency='USD', all_returned_raw_events={},
                raw_events_field_present='events' in result,
                event_scope='ABSENT_OR_EMPTY_RETURNED_EVENTS_NOT_COMPLETE_ACTION_HISTORY', adjusted_close_used=False,
                nominal_price_status='CONDITIONAL_NO_RETURNED_EVENT_FACTOR_ONE_NOT_AUTHENTICATED', cells_checked=214)


def assemble(documents, raw):
    parent, identity, lane = (documents[k] for k in ('parent', 'identity', 'lane'))
    require(parent['schema'] == 'BAD_TAIL_FIVE_SECURITY_107_SESSION_INPUT_PROJECTION_V1', 'Exact parent schema required')
    for obj in (parent, identity, documents['benchmark']):
        require(obj['point_in_time_verified'] is False and obj['promotion_allowed'] is False, 'Parent permission upgrade')
    require(identity['continuous_identity_interval_verified'] is False and identity['provider_price_binding_verified'] is False,
            'Dated identity only')
    require(identity['conditional_window'] == dict(start='2023-03-31', end='2023-05-01'), 'Original 21-day identity boundary differs')
    require(lane['promotion_allowed'] is False and lane['member_point_in_time_verified'] is False and
            lane['fit_performed'] is False and lane['whole_lot_execution_performed'] is False and
            lane['historical_account_outcomes_used_for_selection'] is False, 'Lane scope differs')
    calendar = documents['benchmark']['calendar']
    require(calendar == parent['calendar'] and len(calendar) == 107 and calendar == sorted(set(calendar)) and
            (calendar[0], calendar[-1]) == ('2023-03-31', '2023-09-01'), 'Exact 107 parent and benchmark calendar required')
    require([(d['cutoff'], d['execution_date']) for d in lane['decisions']] == CLOCK, 'Six clocks differ')
    labels = [deepcopy(r) for r in parent['identity_projection']['rows'] if r['ticker'] in COORDINATES]
    enph = [deepcopy(r) for r in identity['rows'] if r['ticker'] == 'ENPH']
    require(len(enph) == 1 and len(labels) == 3, 'Exact inherited identity subset required')
    labels += enph
    for row in labels:
        cik, cusip, _ = COORDINATES[row['ticker']]
        require((row['subject_cik'], row['cusip'], row['security_id'], row['issuer_id']) ==
                (cik, cusip, f'security:{cik}:{cusip}', f'issuer:{cik}'), 'Identity coordinate differs')
        require(row['point_in_time_verified'] is False and row['provider_binding_verified'] is False, 'Identity row upgrade')
    require(len({r['issuer_id'] for r in labels}) == 4, 'Four unique issuers required')
    choices, chains = [], {}
    for decision in lane['decisions']:
        cutoff, execution = decision['cutoff'], decision['execution_date']
        require(calendar[calendar.index(cutoff)+1] == execution, 'Next observed clock differs')
        candidates = decision['lanes']['DRAWDOWN']
        require(len(candidates) == 1, 'Unique frozen DRAWDOWN candidate required')
        candidate = candidates[0]
        expected = {f'security:{cik}:{cusip}': dict(ticker=t, issuer_id=f'issuer:{cik}', risk_chain=chain)
                    for t, (cik, cusip, chain) in COORDINATES.items()}
        require(candidate['selected'] == expected and candidate['holding_count'] == 4 and
                set(candidate['tickers'].split(';')) == set(COORDINATES), 'Selected identities/risk chains differ')
        choices.append(dict(decision_date=cutoff, execution_date=execution, saved_candidate=deepcopy(candidate),
                            queue_reference=deepcopy(decision['queue_reference']), target_weights_materialized=False))
        chains[cutoff] = {sid: row['risk_chain'] for sid, row in expected.items()}
    channel = decode_enph(raw, documents['metadata'], calendar)
    matrices = {kind: {} for kind in ('open', 'close')}
    for kind in matrices:
        source = parent['price_projection']['matrices'][kind]
        require(set(source) == set(calendar), 'Parent price dates differ')
        for day, enph_row in zip(calendar, channel['rows']):
            require(all(type(source[day][t]) is str for t in ('BKR', 'CDNS', 'FTNT')), 'Parent exact strings required')
            for ticker in ('BKR', 'CDNS', 'FTNT'): decimal_string(source[day][ticker])
            matrices[kind][day] = {t: source[day][t] for t in ('BKR', 'CDNS', 'FTNT')}
            matrices[kind][day]['ENPH'] = enph_row[kind]
    channels = [deepcopy(c) for c in parent['price_projection']['channels'] if c['ticker'] in COORDINATES]
    require(len(channels) == 3 and all([r['session'] for r in c['rows']] == calendar for c in channels), 'Inherited channels differ')
    channels.append(channel)
    return dict(schema='DRAWDOWN_FOUR_SECURITY_107_SESSION_CONDITIONAL_INPUT_V1', lane='DRAWDOWN',
        parent_references={role: reference(role) for role in BOUND}, calendar=deepcopy(calendar),
        observed_decision_clock=[list(x) for x in CLOCK], saved_lane_choices=choices,
        selected_risk_chains_by_decision=chains, security_count=4, distinct_issuer_count=4,
        price_projection=dict(tickers=sorted(COORDINATES), ticker_count=4, session_count=107, price_cell_count=856,
            matrices=matrices, channels=channels, matrix_value_encoding='EXACT_DECIMAL_STRINGS',
            nominal_price_status='CONDITIONAL_RECONSTRUCTION_NOT_AUTHENTICATED',
            calendar_status='107_OBSERVED_NY_SESSIONS_EXACT_BENCHMARK_MATCH'),
        identity_projection=dict(rows=labels, conditional_window=dict(start=calendar[0], end=calendar[-1]),
            enph_original_conditional_window=deepcopy(identity['conditional_window']),
            interval_stability_assumption='NEW_EXPLICIT_107_DAY_STABILITY_ASSUMPTION_USING_DATED_FACTS_NOT_INTERVAL_CERTIFICATION',
            parent_identity_assumption=parent['identity_projection']['interval_stability_assumption'],
            enph_original_interval_certification_extended=False, evidence_scope='DATED_FACTS_PLUS_EXPLICIT_CONDITIONAL_ASSUMPTION'),
        downstream_status='FINAL_TARGET_SCHEDULE_NOT_BOUND_OR_VERIFIED', original_parent_assets_modified=False,
        **dict.fromkeys(FALSE, False))


def build():
    archive.strict(LOADED)
    sources, documents, raw = dict(LOADED), {}, None
    for role in BOUND:
        ref = reference(role)
        content = Path(ref['path']).read_bytes()
        require(hashlib.sha256(content).hexdigest() == ref['sha256'], 'Hard parent bytes differ')
        archive.merge(sources, {ref['path']: ref['sha256']})
        if role == 'raw':
            raw = content
            continue
        documents[role] = json.loads(content, object_pairs_hook=unique)
        for key in ('source_hashes', 'historical_expected_source_hashes', 'prepare_source_hashes'):
            if key in documents[role]: archive.merge(sources, documents[role][key])
    contract = archive.load_contract()
    resolution = archive.verify_expected_sources(sources, contract)
    value = assemble(documents, raw)
    require(archive.verify_expected_sources(sources, contract) == resolution, 'Sources changed during assembly')
    archive.strict(LOADED)
    return dict(value, historical_expected_source_hashes=sources, archive_resolution=resolution)


def publish():
    require(not OUTPUT.parent.exists(), 'Fresh fixed namespace required')
    value = build()
    contract = archive.load_contract()
    def verify():
        archive.strict(LOADED)
        require(archive.verify_expected_sources(value['historical_expected_source_hashes'], contract) == value['archive_resolution'], 'Publication source drift')
    verify()
    raw = (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()
    OUTPUT.parent.mkdir(parents=True, exist_ok=False)
    with OUTPUT.open('xb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    verify()
    require(OUTPUT.read_bytes() == raw, 'Published bytes differ')
    return dict(path=str(OUTPUT), sha256=hashlib.sha256(raw).hexdigest())


if __name__ == '__main__':
    print(json.dumps(publish()))
