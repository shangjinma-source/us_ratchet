"""Prepare existing nominal history and local identities; no gross or search."""
import argparse
import csv
import hashlib
import io
import json
import gzip
from datetime import datetime
from zoneinfo import ZoneInfo
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MEMBERS = 'tmp/historical_official_event_overlay_20261014_v1/coverage.json'
PANEL = 'tmp/current_ohlc_actual_projection_20261013_v1/panel.json'
IDENTITIES = 'data/cache/candidate_pools/ndx_taxonomy_v2/security_identity.csv'
RAW = 'data/cache/candidate_pools/ndx_fundamentals/price_basis_v1/raw'
PINS = {
    MEMBERS: 'eb6758a73b93234a8258eef15d9eeae5da2c594387e79ebb1839a720f41a691f',
    PANEL: '92361a7321765594a5544ab3cb9128410c8296799d99b3d23090e24a37df9822',
}


def prepare():
    sources = {}

    def read(relative, expected=None):
        data = (ROOT / relative).read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if expected is not None and digest != expected:
            raise ValueError('Source hash differs: ' + relative)
        sources[relative] = digest
        return data

    def read_csv(relative, manifest=True):
        declaration = json.loads(read(relative + '.manifest.json')) if manifest else None
        data = read(relative, declaration['content_sha256'] if declaration else None)
        rows = list(csv.DictReader(io.StringIO(data.decode('utf-8-sig'))))
        if declaration and len(rows) != declaration['row_count']:
            raise ValueError('Row count differs: ' + relative)
        return rows, declaration

    membership = json.loads(read(MEMBERS, PINS[MEMBERS]))
    panel = json.loads(read(PANEL, PINS[PANEL]))
    calendar = panel['calendar']
    quote_sources = {}
    for ticker in ('DASH', 'ROP'):
        base = 'data/cache/research/current_raw_capture_20261013_v1/' + ticker
        receipt = json.loads(read(base + '.receipt.json'))
        raw = read(base + '.response.bin', receipt['raw_sha256'])
        decoded = gzip.decompress(raw) if raw[:2] == b'\x1f\x8b' else raw
        provider = json.loads(decoded)['chart']['result'][0]
        if provider['meta']['symbol'] != ticker:
            raise ValueError('Wrong provider symbol')
        zone = ZoneInfo(provider['meta']['exchangeTimezoneName'])
        quote_dates = [datetime.fromtimestamp(t, zone).date().isoformat() for t in provider['timestamp']]
        quote_closes = dict(zip(quote_dates, provider['indicators']['quote'][0]['close']))
        stock = next(s for s in panel['stocks'] if s['ticker'] == ticker)
        if any(quote_closes.get(d) != values[3] for d, values in zip(calendar, stock['values'])):
            raise ValueError('Panel differs from raw quote channel')
        quote_sources[ticker] = (quote_closes, provider.get('events', {}).get('splits', {}), zone)
    identities, _ = read_csv(IDENTITIES)
    reports, _ = read_csv('data/cache/candidate_pools/ndx_history/qqq_nport_constituents.csv')
    # Preserve and bind the existing dated FISV/FI rule; no successor aliases.
    import yaml
    lifecycle = yaml.safe_load(read('config/ndx_security_lifecycle.yaml'))
    alias_rules = [r for r in lifecycle['rules'] if r['rule_id'] in
                   ('fiserv_fisv_to_fi_2023', 'meta_fb_to_meta_2022')]
    cache = {}

    def nominal(ticker):
        if ticker not in cache:
            path = RAW + '/' + ticker + '.csv'
            if not (ROOT / path).exists():
                cache[ticker] = ({}, None, path)
            else:
                rows, declaration = read_csv(path)
                if not (declaration['price_basis'] == 'unadjusted_nominal_trade_price'
                        and declaration['valuation_use_only'] is True
                        and declaration['corporate_action_adjustment'] == 'none'):
                    raise ValueError('Unexpected nominal basis: ' + ticker)
                by_date = {r['Date']: r for r in rows}
                if len(by_date) != len(rows):
                    raise ValueError('Duplicate raw dates: ' + ticker)
                cache[ticker] = (by_date, declaration, path)
        return cache[ticker]

    windows = []
    for window in membership['dates']:
        decision = window['decision_cutoff']
        if decision > '2024-05-31':
            raise ValueError('Unexpected later decision')
        end = calendar.index(decision)
        days = calendar[end-252:end+1]
        if len(days) != 253 or len(window['corrected_members']) != 101:
            raise ValueError('Full denominator and training history required')
        rows = []
        for member in window['corrected_members']:
            ticker = member['ticker']
            matches = [r for r in identities if ticker in r['ticker_set'].split(';')]
            all_matches = matches
            observations = [r for r in reports if r['ticker'] == ticker
                            and r['report_date'] <= decision and r['available_date'] <= decision]
            if observations:
                latest = max(r['report_date'] for r in observations)
                cusips = {r['cusip'] for r in observations if r['report_date'] == latest}
                matches = [r for r in matches if r['cusip'] in cusips]
            declarations = {(r['security_id'], r['issuer_id']) for r in matches
                            if r['identity_status'] == 'resolved'}
            unique = len(declarations) == 1 and all(r['identity_status'] == 'resolved' for r in matches)
            sid, issuer = next(iter(declarations)) if unique else (None, None)
            closes, missing, paths, aliases = [], [], set(), []
            for day in days:
                price_ticker = ticker
                rules = [r for r in alias_rules if ticker in r['recognized_tickers']]
                if rules:
                    if len(rules) != 1:
                        raise ValueError('Ambiguous ticker lifecycle')
                    applicable = [r for r in rules[0]['intervals']
                                  if (r['effective_from'] is None or str(r['effective_from']) <= day)
                                  and (r['effective_to'] is None or day <= str(r['effective_to']))]
                    if len(applicable) != 1:
                        raise ValueError('Ambiguous dated alias mapping')
                    price_ticker = applicable[0]['price_ticker']
                    if price_ticker != ticker:
                        aliases.append({'date': day, 'price_ticker': price_ticker})
                raw, declaration, path = nominal(price_ticker)
                paths.add(path)
                value = raw.get(day, {}).get('Close')
                try:
                    valid = value is not None and Decimal(value).is_finite() and Decimal(value) > 0
                except InvalidOperation:
                    valid = False
                closes.append(value if valid else None)
                if not valid:
                    missing.append(day)
            reasons = []
            if not unique:
                reasons.append('LOCAL_IDENTITY_MISSING_OR_AMBIGUOUS')
            if missing:
                reasons.append('INCOMPLETE_MATURE_253_NOMINAL_CLOSE_HISTORY')
            training = closes
            basis = 'NOMINAL'
            returned_splits = []
            if ticker in quote_sources:
                quotes, splits, zone = quote_sources[ticker]
                training = [str(quotes[d]) if quotes.get(d) is not None else None for d in days]
                if all(v is not None and Decimal(v).is_finite() and Decimal(v) > 0 for v in training) and closes[-1] is not None:
                    reasons = [r for r in reasons if r != 'INCOMPLETE_MATURE_253_NOMINAL_CLOSE_HISTORY']
                else:
                    reasons.append('INCOMPLETE_QUOTE_HISTORY_OR_NOMINAL_DECISION_COST')
                basis = 'CONDITIONAL_PROVIDER_QUOTE_SPLIT_ADJUSTED'
                returned_splits = [event for event in splits.values() if days[0] <=
                    datetime.fromtimestamp(event['date'], zone).date().isoformat() <= decision]
            rows.append(dict(ticker=ticker, security_id=sid, issuer_id=issuer,
                eligible_for_pending_split_validation=not reasons, exclusion_reasons=reasons,
                identity_evidence=matches, other_historical_identity_rows=[r for r in all_matches if r not in matches],
                identity_resolution='LATEST_AVAILABLE_NPORT_CUSIP' if observations else 'UNIQUE_LOCAL_MAPPING_WITHOUT_ASOF_NPORT', identity_source=IDENTITIES,
                identity_available_by_cutoff=unique and any(r['available_from'] <= decision for r in matches),
                identity_status='UNIQUE_LOCAL_MAPPING_NOT_PIT_AUTHENTICATED' if unique else 'UNRESOLVED',
                nominal_close=closes, missing_training_dates=missing, raw_paths=sorted(paths),
                training_basis=basis, training_close=training, decision_nominal_close=closes[-1],
                training_source=PANEL if ticker in quote_sources else sorted(paths),
                returned_provider_splits_in_training=returned_splits if ticker in quote_sources else None,
                provider_event_completeness_authenticated=False,
                quote_gross_rule='END_OVER_START_WITHOUT_EXTRA_SPLIT_MULTIPLIER' if ticker in quote_sources else None,
                dated_aliases=aliases, membership_evidence=member))
        eligible = [r for r in rows if r['eligible_for_pending_split_validation']]
        groups = {}
        for row in rows:
            if row['issuer_id']:
                groups.setdefault(row['issuer_id'], []).append(row['ticker'])
        windows.append(dict(decision_cutoff=decision, member_denominator=101,
            eligible_count=len(eligible), eligible_issuer_count=len({r['issuer_id'] for r in eligible}),
            same_issuer_classes={k:v for k,v in groups.items() if len(v)>1},
            training_dates=days, scenario_start_dates=days[:-1:21], scenario_end_dates=days[21::21],
            candidates=rows))
    if len(windows) != 15:
        raise ValueError('Expected fifteen decisions')
    for relative, digest in sources.items():
        if hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() != digest:
            raise ValueError('Source changed during preparation')
    return dict(status='PREPARED_NOMINAL_HISTORY_PENDING_SPLIT_REGISTRY_V2', windows=windows,
        source_hashes=sources, training_gross_generated=False, search_calls=0, network_calls=0,
        future_outcome_used_for_eligibility=False, point_in_time_identity_authenticated=False,
        nominal_is_adjusted_return=False, price_basis='PER_CANDIDATE_TRAINING_BASIS_WITH_SINA_NOMINAL_DECISION_COST',
        next_step='Review split registry v2 before converting twelve 21-session endpoint ratios; no raw nominal return ratios authorized here.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    destination = Path(args.output).resolve()
    if (ROOT / 'tmp').resolve() not in destination.parents or destination.exists():
        raise ValueError('Create-only tmp output required')
    result = prepare()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    print(json.dumps([{'decision': w['decision_cutoff'], 'eligible': w['eligible_count'],
        'excluded': [r['ticker'] for r in w['candidates'] if r['exclusion_reasons']]}
        for w in result['windows']]))
