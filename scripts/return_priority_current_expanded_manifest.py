"""Prepare the complete current declared domain; no selector, search or book."""
from pathlib import Path
import gzip
import hashlib
import json
from datetime import datetime
from fractions import Fraction
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'tmp/current_expanded_rebased_manifest_20261015_v1.json'
OLD = 'tmp/current_quantity_prepared_20261014_v2.json'
IDENTITY = 'tmp/next12_identity_admission_20261014_v1/identity_admission.json'
COORDINATE = 'tmp/next12_coordinate_review_20261014_v1/coordinate_review.json'
SPECIAL = 'tmp/next12_nonsimple_final_admission_20261014_v1.json'
MRNA = 'tmp/mrna_august_jump_primary_crosscheck_20261014_v2.json'
RAW = 'data/cache/research/current_raw_capture_20261014_v1'
ASOF = '2026-10-13'


def main():
    if OUTPUT.exists():
        raise FileExistsError(OUTPUT)
    pins = {}

    def pin(path, expected=None):
        p = Path(path)
        if not p.is_absolute():
            p = ROOT / p
        key = p.resolve().relative_to(ROOT).as_posix()
        digest = hashlib.sha256(p.read_bytes()).hexdigest()
        if expected is not None and digest != expected:
            raise ValueError(f'Source changed: {key}')
        pins[key] = digest
        return key

    def read(path):
        return json.loads((ROOT / pin(path)).read_text(encoding='utf-8'))

    old, identity, coordinate, special = [read(p) for p in (OLD, IDENTITY, COORDINATE, SPECIAL)]
    read(MRNA)
    # Historical receipts retain their old code pins; only immutable source evidence
    # is inherited. No old mutable implementation is presented as currently verified.
    for evidence in (old, identity, coordinate, special):
        for path, digest in evidence.get('source_hashes', {}).items():
            if Path(path).suffix != '.py':
                pin(path, digest)
    pin(__file__)

    def raw(ticker):
        path = f'{RAW}/{ticker}.response.bin'
        receipt_path = f'{RAW}/{ticker}.receipt.json'
        receipt = read(receipt_path)
        pin(path, receipt['raw_sha256'])
        data = (ROOT / path).read_bytes()
        channel = json.loads(gzip.decompress(data) if data[:2] == b'\x1f\x8b' else data,
                             parse_float=str)['chart']['result'][0]
        meta = channel['meta']
        if meta['symbol'] != ticker or meta['currency'] != 'USD':
            raise ValueError(f'Metadata mismatch: {ticker}')
        tz = ZoneInfo(meta['exchangeTimezoneName'])
        dates = [datetime.fromtimestamp(v, tz).date().isoformat() for v in channel['timestamp']]
        if len(dates) != len(set(dates)):
            raise ValueError(f'Duplicate date: {ticker}')
        closes = dict(zip(dates, channel['indicators']['quote'][0]['close']))
        events = []
        for kind, values in channel.get('events', {}).items():
            for event in values.values():
                events.append({'kind': kind, 'date': datetime.fromtimestamp(event['date'], tz).date().isoformat(),
                               'payload': event})
        return path, receipt_path, closes, events, meta

    _, _, qqq, _, _ = raw('QQQ')
    dates = sorted(d for d, close in qqq.items() if d <= ASOF and close is not None)[-253:]
    assert dates == old['training_dates'] and len(dates) == 253 and dates[-1] == ASOF
    extra = {r['ticker']: r for r in identity['rows']}
    candidates, exclusions = [], []
    for previous in old['coverage']:
        ticker = previous['ticker']
        path, receipt, closes, events, meta = raw(ticker)
        values = [closes.get(d) for d in dates]
        missing = [d for d, value in zip(dates, values) if value is None]
        existing = previous['identity'] or extra.get(ticker)
        identity_refs = [OLD] if previous['identity'] else [IDENTITY]
        if ticker in extra and not previous['identity']:
            identity_refs += extra[ticker]['source_references']
        identity_refs = [pin(p) for p in identity_refs]
        blockers = []
        factors, shares = [], []
        refs = [COORDINATE]
        rule = 'UNCHANGED_WHOLE_QUOTE_CLOSE'
        if ticker in ('HON', 'CMCSA', 'WDC'):
            reviewed = special['tickers'][ticker]
            assert Path(reviewed['source_path']).as_posix() == path
            rule = 'RESTORED_PARENT_PRICE_ONLY'
            refs = [SPECIAL]
            factors = [dict(e, source_references=[SPECIAL]) for e in reviewed['price_coordinate_factors']]
            shares = [dict(e, source_references=[SPECIAL]) for e in reviewed['true_share_events']]
            observed = {(e['date'], str(Fraction(e['payload']['numerator']) / Fraction(e['payload']['denominator'])))
                        for e in events if e['kind'] == 'splits'}
            expected = {(e['date'], str(Fraction(e['factor']))) for e in factors}
            if observed != expected:
                blockers.append('NONSIMPLE_PROVIDER_EVENT_SET_DIFFERS_FROM_REVIEW')
        elif ticker in coordinate['tickers']:
            reviewed = coordinate['tickers'][ticker]
            if reviewed['source_path'].replace('\\', '/') != path:
                blockers.append('WHOLE_RAW_DIFFERS_FROM_COORDINATE_REVIEW')
            for event in events:
                if event['kind'] != 'splits' or event['date'] < dates[0]:
                    continue
                ratio = str(Fraction(event['payload']['numerator']) / Fraction(event['payload']['denominator']))
                matches = [e for e in reviewed['events'] if e['date'] == event['date'] and e['provider_ratio'] == ratio
                           and e['share_multiplier_allowed']]
                if not matches:
                    blockers.append('UNREVIEWED_SPLIT:' + event['date'])
                else:
                    event_refs = [COORDINATE, matches[0]['official_source']]
                    event_refs = [pin(p) for p in event_refs if p]
                    factors.append({'date': event['date'], 'factor': ratio, 'source_references': event_refs})
                    shares.append({'date': event['date'], 'ratio': ratio, 'source_references': event_refs})
        elif ticker not in ('SPCX', 'HONA'):
            blockers.append('NO_COORDINATE_REVIEW')
        for event in events:
            if event['kind'] not in ('splits', 'dividends') and dates[0] <= event['date'] <= ASOF:
                blockers.append('UNKNOWN_ACTION:' + event['kind'])
        if existing is None and ticker not in ('SPCX', 'HONA'):
            blockers.append('IDENTITY_UNRESOLVED')
        status = 'READY_CONDITIONAL'
        if missing:
            if ticker in ('SPCX', 'HONA'):
                status = 'EXCLUDED_TRAINING_RULE'
                exclusions.append({'ticker': ticker, 'reason': 'INSUFFICIENT_253_SESSION_PREDECISION_HISTORY',
                                   'known_asof': ASOF, 'source_references': [path, OLD, IDENTITY]})
            else:
                blockers.append('MISSING_PREDECISION_CLOSE')
        if blockers:
            status = 'BLOCKED'
        factor = Fraction(1)
        for event in factors:
            if event['date'] > ASOF:
                factor *= Fraction(event['factor'])
        cost = str(Fraction(closes[ASOF]) * factor) if closes.get(ASOF) is not None else None
        candidates.append({'ticker': ticker, 'security_id': existing['security_id'] if existing else None,
                           'issuer_id': existing['issuer_id'] if existing else None, 'status': status,
                           'identity_reviewed': existing is not None, 'coordinate_reviewed': not blockers,
                           'identity_source_references': identity_refs, 'training_source': path,
                           'raw_close': values, 'training_rule': rule, 'price_coordinate_factors': factors,
                           'true_share_events': shares, 'decision_nominal_close': cost,
                           'coordinate_source_references': [pin(p) for p in refs] + [path, receipt],
                           'blockers': blockers, 'missing_training_dates': missing,
                           'raw_first_session': min(closes), 'raw_last_session': max(closes),
                           'source_metadata': {k: meta.get(k) for k in ('symbol', 'currency', 'instrumentType', 'exchangeTimezoneName')},
                           'returned_events': events, 'previous_exclusion_reasons': previous['exclusion_reasons'],
                           'qualification_certified': False})
    members = [r['ticker'] for r in candidates]
    result = {'schema': 'CURRENT_EXPANDED_REBASED_MANIFEST_V1', 'decision_date': ASOF,
              'status': 'BLOCKED' if any(r['blockers'] for r in candidates) else 'READY_CONDITIONAL_MANIFEST',
              'training_dates': dates, 'members': members, 'candidates': candidates,
              'admission': {'decision_date': ASOF, 'status': 'REVIEWED_CONDITIONAL', 'members': members,
                            'training_exclusions': exclusions, 'source_references': [OLD, IDENTITY, COORDINATE, SPECIAL, MRNA]},
              'source_hashes': pins, 'full_domain_count': len(members),
              'ready_count': sum(r['status'] == 'READY_CONDITIONAL' for r in candidates),
              'limitations': ['Declared current101 universe retained; not certified PIT membership.',
                              'Identity continuity is conditional source review, not exhaustive corporate-action certification.',
                              'Whole-provider price-only training excludes dividends and distributed rights.',
                              'Coordinate restoration is conditional research, not authenticated live nominal execution price.',
                              'MRNA August jump retained under saved primary and independent price crosscheck.',
                              'SPCX/HONA missing history is not imputed or inherited from a parent.'],
              'network_calls': 0, 'selection_calls': 0, 'book_calls': 0,
              'research_only': True, 'execution_blocked': True}
    with OUTPUT.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False)
    print(json.dumps({'path': str(OUTPUT), 'sha256': hashlib.sha256(OUTPUT.read_bytes()).hexdigest(),
                      'status': result['status'], 'ready': result['ready_count'],
                      'blocked': [(r['ticker'], r['blockers']) for r in candidates if r['blockers']]}))


if __name__ == '__main__':
    main()
