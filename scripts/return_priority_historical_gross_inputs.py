"""Pure conditional price-scenario preparation. Never imports or calls search."""
import argparse
import hashlib
import json
from fractions import Fraction
from pathlib import Path


def positive(value):
    if isinstance(value, bool):
        raise ValueError('Boolean price/factor')
    result = Fraction(str(value))
    if result <= 0:
        raise ValueError('Nonpositive price/factor')
    return result


def prepare(data, events):
    """Build core kwargs; input identity/eligibility is retained, not certified.

    Split boundary is start < event <= end. Provider-adjusted sequences never
    receive another split multiplier. Events after cutoff are not inspected.
    """
    output = []
    for window in data['windows']:
        cutoff = window['decision_cutoff']
        dates = window['training_dates']
        starts, ends = window['scenario_start_dates'], window['scenario_end_dates']
        if len(dates) != 253 or dates != sorted(set(dates)) or dates[-1] != cutoff:
            raise ValueError('Require 253 distinct mature session dates ending at cutoff')
        if starts != dates[0:252:21] or ends != dates[21:253:21]:
            raise ValueError('Require twelve contiguous nonoverlapping 21-session intervals')
        candidates = window['candidates']
        if len(candidates) != window['member_denominator']:
            raise ValueError('Member denominator changed')
        known = {}
        for event in events:
            when = event['event_date']
            if when > cutoff or when <= dates[0]:
                continue
            if not event.get('conditional_unit_conversion_event'):
                raise ValueError('Unaccepted conversion event')
            if event.get('event_type', 'SIMPLE_SPLIT') != 'SIMPLE_SPLIT':
                raise ValueError('Non-split event cannot convert parent shares')
            key = (event['ticker'], when)
            factor = positive(event['new_shares']) / positive(event['old_shares'])
            if 'factor' in event and positive(event['factor']) != factor:
                raise ValueError('Inconsistent event factor')
            if key in known and known[key] != factor:
                raise ValueError('Conflicting duplicate split')
            known[key] = factor
        prices, metadata, scenarios = {}, {}, [{} for _ in ends]
        exclusions, coverage = [], []
        for candidate in candidates:
            ticker, sid = candidate['ticker'], candidate['security_id']
            reasons = list(candidate['exclusion_reasons'])
            if not candidate['eligible_for_pending_split_validation']:
                reasons.append('INPUT_NOT_ELIGIBLE')
            values = candidate['training_close']
            if len(values) != 253 or any(v is None for v in values):
                reasons.append('INCOMPLETE_TRAINING_HISTORY')
            basis = candidate['training_basis']
            if basis not in ('NOMINAL', 'CONDITIONAL_PROVIDER_QUOTE_SPLIT_ADJUSTED'):
                reasons.append('UNSUPPORTED_TRAINING_BASIS')
            if candidate['decision_nominal_close'] is None:
                reasons.append('MISSING_DECISION_NOMINAL_PRICE')
            row = {'ticker': ticker, 'security_id': sid, 'training_basis': basis,
                   'past_missing_dates': candidate.get('missing_training_dates', []),
                   'identity_status': candidate.get('identity_status'),
                   'applied_events': []}
            if reasons:
                exclusions.append(dict(row, reasons=sorted(set(reasons))))
                coverage.append(dict(row, included=False))
                continue
            if not sid or not candidate['issuer_id'] or sid in prices:
                raise ValueError('Missing or duplicate identity')
            closes = [positive(value) for value in values]
            prices[sid] = str(positive(candidate['decision_nominal_close']))
            metadata[sid] = {'ticker': ticker, 'issuer_id': candidate['issuer_id']}
            for index, (start, end) in enumerate(zip(starts, ends)):
                factor = Fraction(1)
                if basis == 'NOMINAL':
                    for (symbol, when), ratio in sorted(known.items()):
                        if symbol == ticker and start < when <= end:
                            factor *= ratio
                            row['applied_events'].append({'date': when, 'factor': str(ratio), 'scenario_index': index})
                scenarios[index][sid] = str(closes[(index + 1) * 21] / closes[index * 21] * factor)
            coverage.append(dict(row, included=True))
        output.append({'decision_cutoff': cutoff, 'member_denominator': len(candidates),
                       'included_count': len(prices), 'exclusions': exclusions, 'coverage': coverage,
                       'search_arguments': {'prices': prices, 'metadata': metadata,
                         'entered_cash': '20000', 'fee_bps': '0', 'minimum_cash_buffer': '0',
                         'training_scenarios': scenarios, 'scenario_dates': ends,
                         'decision_date': cutoff, 'max_objective_evaluations': 8192,
                         'fixed_seed': 'fresh-quantity-20261014-v1'}})
    return {'windows': output, 'source_hashes': dict(data.get('source_hashes', {})),
            'research_only': True, 'search_calls': 0, 'future_outcome_used': False,
            'scope': 'Conditional price-only training scenarios; no dividend/spinoff proceeds; not complete corporate-action coverage or authenticated PIT; no forecast.'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--prepared', required=True)
    parser.add_argument('--events', required=True)
    parser.add_argument('--notes', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    paths = [Path(args.prepared), Path(args.events), Path(args.notes)]
    blobs = [path.read_bytes() for path in paths]
    data, events, notes = [json.loads(blob) for blob in blobs]
    result = prepare(data, events + notes['conditional_split_supplement'])
    result['source_hashes'].update({str(path): hashlib.sha256(blob).hexdigest() for path, blob in zip(paths, blobs)})
    result['source_hashes'][str(Path(__file__))] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    main()
