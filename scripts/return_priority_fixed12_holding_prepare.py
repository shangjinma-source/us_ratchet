"""Prepare all candidates' same-source nextOpen inputs; never select or value."""
import argparse
import csv
import gzip
import hashlib
import json
from copy import deepcopy
from datetime import datetime
from fractions import Fraction
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
FIELDS = ('open', 'high', 'low', 'close')


def factor_on_date(decision_factor, reviewed_events, date):
    factor = Fraction(decision_factor)
    for event in reviewed_events:
        if event['event_date'] <= date:
            factor /= Fraction(event['factor'])
    return factor


def bind_frozen_weights(window, weights):
    """Only bind an already frozen selection; never inspect outcome coverage."""
    result = deepcopy(window['outcome_arguments_without_target_weights'])
    if any(sid not in result['metadata'] or Fraction(value) <= 0 for sid, value in weights.items()):
        raise ValueError('Unknown or nonpositive frozen selection')
    if sum(Fraction(v) for v in weights.values()) > 1:
        raise ValueError('Weights exceed available cash')
    result['target_weights'] = deepcopy(weights)
    return result


def prepare(training_path):
    pins, cached = {}, {}

    def read(path, expected=None):
        path = Path(path)
        if not path.is_absolute():
            path = ROOT / path
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if expected and digest != expected:
            raise ValueError('Changed input: ' + str(path))
        pins[str(path)] = digest
        return raw

    training = json.loads(read(training_path))
    for path, digest in training['source_hashes'].items():
        read(path, digest)
    coverage = json.loads(read('tmp/fixed12_data_coverage_20261014_v3/coverage.json'))
    calendars = {w['decision_cutoff']: w['outcome_dates'] for w in coverage['windows']}
    facts_path = 'tmp/fixed12_official_actions_20261014_v1/observed_primary_facts.json'
    facts = json.loads(read(facts_path))
    merger = next(e for e in facts['events'] if e['ticker'] == 'ANSS')
    terms_path = 'tmp/fixed12_official_actions_20261014_v1/anss_fractional_terms_web_observation.json'
    terms = json.loads(read(terms_path))
    for path in ('backtest/return_priority_holding_entitlement_outcome.py',
                 'backtest/return_priority_cash_stock_entitlements.py',
                 'backtest/return_priority_frozen_nominal_outcome.py'):
        read(path)

    def source(path, ticker):
        key = str(path)
        if key in cached:
            return cached[key]
        raw = read(path)
        if str(path).endswith('.csv'):
            records = list(csv.DictReader(raw.decode('utf-8-sig').splitlines()))
            if len({r['Date'] for r in records}) != len(records):
                raise ValueError('Duplicate archive dates')
            rows = {r['Date']: {k: r[k.title()] for k in FIELDS} for r in records}
            events = []
        elif str(path).endswith('.response.bin'):
            receipt = json.loads(read(str(path).replace('.response.bin', '.receipt.json')))
            if hashlib.sha256(raw).hexdigest() != receipt['raw_sha256']:
                raise ValueError('Receipt mismatch')
            decoded = gzip.decompress(raw) if raw[:2] == b'\x1f\x8b' else raw
            if receipt.get('decoded_sha256') and hashlib.sha256(decoded).hexdigest() != receipt['decoded_sha256']:
                raise ValueError('Decoded mismatch')
            provider = json.loads(decoded)['chart']['result'][0]
            if provider['meta']['symbol'] != ticker or provider['meta']['currency'] != 'USD':
                raise ValueError('Wrong source identity or currency')
            zone = ZoneInfo(provider['meta']['exchangeTimezoneName'])
            day = lambda t: datetime.fromtimestamp(t, zone).date().isoformat()
            dates = [day(t) for t in provider['timestamp']]
            quotes = provider['indicators']['quote'][0]
            if len(set(dates)) != len(dates) or any(len(quotes[k]) != len(dates) for k in FIELDS):
                raise ValueError('Malformed timeline')
            rows = {d: {k: str(quotes[k][i]) for k in FIELDS if quotes[k][i] is not None}
                    for i, d in enumerate(dates)}
            events = [dict(event_date=day(e['date']), factor=str(Fraction(str(e['numerator'])) / Fraction(str(e['denominator']))))
                      for e in provider.get('events', {}).get('splits', {}).values()]
        else:
            raise ValueError('Unsupported training whole source: ' + str(path))
        cached[key] = rows, events
        return rows, events

    qqq_path = 'data/cache/research/current_raw_capture_20261013_v1/QQQ.response.bin'
    qqq, qqq_events = source(qqq_path, 'QQQ')
    if qqq_events:
        raise ValueError('QQQ coordinate events need review')
    windows = []
    for window in training['windows']:
        decision = window['decision_cutoff']
        days = calendars[decision]
        if len(days) != 21 or days != sorted(set(days)) or days[0] <= decision:
            raise ValueError('Expected next21 sessions')
        by_ticker = {r['ticker']: r for r in window['candidates']}
        prices, references, metadata, gaps, records, splits = {}, {}, {}, [], [], []
        for row in window['candidates']:
            ticker, sid, path = row['ticker'], row['security_id'], row['training_source']
            raw_rows, raw_events = source(path, ticker)
            reviewed = [r['event'] for r in row.get('cost_restoration_evidence', [])
                        if r['event']['event_date'] > decision]
            # Archive rows already use their own contemporaneous parent units.
            is_archive = str(path).endswith('.csv')
            factor = Fraction(1 if is_archive else row['decision_cost_factor'])
            if not is_archive:
                future_events = {(e['event_date'], Fraction(e['factor'])) for e in raw_events if e['event_date'] > decision}
                admitted = {(e['event_date'], Fraction(e['factor'])) for e in reviewed}
                if future_events != admitted:
                    raise ValueError('Unreviewed coordinate event: ' + ticker)
            observed = raw_rows.get(decision, {}).get('close')
            if observed is None or row['decision_cost'] is None or Fraction(observed) * factor != Fraction(row['decision_cost']):
                raise ValueError('Decision cost bridge differs: ' + ticker)
            metadata[sid] = dict(ticker=ticker, issuer_id=row['issuer_id'])
            references[sid] = [path]
            prices[sid] = {}
            for date in days:
                bridge = factor_on_date(factor, reviewed, date) if not is_archive else Fraction(1)
                values = raw_rows.get(date, {})
                prices[sid][date] = {k: str(Fraction(v) * bridge) for k, v in values.items()}
                terminal = ticker == 'ANSS' and date >= merger['effective_date']
                required = [] if terminal else (['open', 'close'] if date == days[0] else ['close'])
                for field in FIELDS:
                    value = prices[sid][date].get(field)
                    if value is None or Fraction(value) <= 0:
                        gaps.append(dict(ticker=ticker, security_id=sid, date=date, field=field,
                                         required_for_holding=field in required))
            for event in reviewed:
                if decision < event['event_date'] <= days[-1]:
                    ratio = Fraction(event['factor'])
                    splits.append(dict(date=event['event_date'], security_id=sid,
                        new_shares=ratio.numerator, old_shares=ratio.denominator,
                        source_references=[path, str(training_path)]))
            records.append(dict(ticker=ticker, security_id=sid, training_status=row['status'],
                training_exclusion_reasons=row['exclusion_reasons'], source=path,
                decision_cost=row['decision_cost'], decision_factor=str(factor), same_whole_source=True))
        mixed, settlements = [], {}
        if decision < merger['effective_date'] <= days[-1] and 'ANSS' in by_ticker:
            old, new = by_ticker['ANSS']['security_id'], by_ticker['SNPS']['security_id']
            event_id = 'ANSS_SNPS_2025_07_17_CONDITIONAL_END_OF_SESSION'
            mixed.append(dict(event_id=event_id, old_sid=old, new_sid=new, effective_date=merger['effective_date'],
                effective_time_confirmed=True, eligibility_confirmed=True,
                effective_time_basis='DAILY_END_OF_SESSION_CONDITIONAL_COMPLETION_DATE',
                limitations=['No opening or intraday effective-time confirmation; no trading permitted.',
                             'Payment and stock delivery dates unknown; rights remain nontradable.'],
                cash_per_share=merger['cash_per_share_usd'], new_shares_per_old_share=merger['new_shares_per_old_share'],
                source_references=[facts_path, merger['source_url']]))
            reference_date = terms['reference_session']
            reference_price = prices[new][reference_date]['close']
            settlements[event_id] = dict(known_asof=merger['effective_date'],
                fraction_reference_close=dict(date=reference_date, price=reference_price, source_references=references[new]),
                reference_is_previous_closing_session=True, fraction_cash_rounding=terms['rounding'],
                source_references=[terms_path, terms['source_url']], price_basis='CONDITIONAL_PROVIDER_CLOSE_NOT_EXCHANGE_CERTIFIED',
                payment_date=None)
        arguments = dict(nominal_prices=prices, metadata=metadata, session_dates=[decision] + days,
            decision_date=decision, end_date=days[-1], entered_cash=training['protocol']['entered_cash'],
            fee_bps='0', split_events=splits, cash_merger_events=[], unmodelled_action_events=[],
            cash_stock_merger_events=mixed, fractional_settlements=settlements, price_source_references=references)
        windows.append(dict(decision_cutoff=decision, candidates=records, price_gaps=gaps,
            outcome_arguments_without_target_weights=arguments,
            qqq_reference=dict(source=qqq_path, basis='CONDITIONAL_PROVIDER_PRICE_ONLY_NO_RETURNED_SPLITS',
                nominal_prices={d: qqq.get(d, {}) for d in days}, target_weight='1',
                outcome_arguments=dict(target_weights={'reference:QQQ': '1'},
                    nominal_prices={'reference:QQQ': {d: qqq.get(d, {}) for d in days}},
                    metadata={'reference:QQQ': {'ticker': 'QQQ', 'issuer_id': 'reference:QQQ'}},
                    session_dates=[decision] + days, decision_date=decision, end_date=days[-1],
                    entered_cash=training['protocol']['entered_cash'], fee_bps='0',
                    split_events=[], cash_merger_events=[], unmodelled_action_events=[]),
                missing_dates=[d for d in days if not qqq.get(d, {}).get('close') or d == days[0] and not qqq.get(d, {}).get('open')]),
            selection_changed=False, outcome_calls=0))
    read(__file__)
    for path, digest in list(pins.items()):
        read(path, digest)
    return dict(status='ALL_CANDIDATE_HOLDING_INPUTS_PREPARED_NO_SELECTION_OR_VALUATION',
        training_input=str(training_path), windows=windows, source_hashes=pins, outcome_calls=0, search_calls=0,
        future_prices_used_for_eligibility=False, research_only=True, execution_blocked=True,
        limitations=['Conditional nominal coordinates, not exchange-certified prices or dividend-inclusive returns.',
                    'ANSS cash and successor shares remain unpaid/undelivered nontradable rights.',
                    'Bind only frozen selected target_weights later; never filter candidates using these price gaps.',
                    'No rounding of provider SNPS Close before contractual fractional cash rounding.'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--training', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    destination = args.output.resolve()
    if destination.exists() or (ROOT / 'tmp').resolve() not in destination.parents:
        raise ValueError('Create-only tmp output required')
    result = prepare(args.training)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    print(json.dumps(dict(windows=len(result['windows']), outcome_calls=0, search_calls=0)))
