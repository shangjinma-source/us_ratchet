"""Offline feasibility counts, not signals or a performance backtest."""
import argparse
from collections import defaultdict
from datetime import datetime
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
from zoneinfo import ZoneInfo


def build(inventory, queue):
    windows = []
    for window in inventory['windows']:
        matches = [item for item in queue['windows']
                   if item['book_sha256'] == window['frozen_book']['sha256']]
        if len(matches) != 1:
            raise ValueError('EXPOSURE_BOOK_BINDING_REQUIRED')
        held = {row['security_id']: set(row['held_sessions']) for row in matches[0]['rows']}
        records = []
        missing = []
        for row in window['rows']:
            security = row['security_id']
            if security not in held:
                continue
            issuer = inventory['issuers'].get(row.get('cik'), {})
            groups = defaultdict(list)
            for index in row['candidate_event_indices']:
                event = issuer['events'][index]
                key = (event['accession'], event['acceptance'], event['unit'],
                       json.dumps(event['current_period'], sort_keys=True),
                       json.dumps(event['prior_period'], sort_keys=True))
                groups[key].append(event)
            count = 0
            for key, events in groups.items():
                revenue = [event for event in events if event['concept'] in
                           ('RevenueFromContractWithCustomerExcludingAssessedTax', 'Revenues')]
                income = [event for event in events if event['concept'] == 'NetIncomeLoss']
                if len(revenue) != 1 or len(income) != 1:
                    continue  # Never select a convenient revenue concept from competing alternatives.
                count += 1
                accepted = datetime.fromisoformat(key[1]).astimezone(ZoneInfo('America/New_York'))
                records.append(dict(security_id=security, tickers=row['tickers'], accession=key[0],
                    acceptance=key[1], current_period=revenue[0]['current_period'],
                    revenue_change=revenue[0]['absolute_change'], income_change=income[0]['absolute_change'],
                    both_absolute_changes_negative=all(Fraction(event['absolute_change']) < 0
                                                       for event in (revenue[0], income[0])),
                    baseline_held_on_acceptance_date=accepted.date().isoformat() in held[security],
                    original_verified_in_inventory=all(event['original_filing_text_verified']
                                                       for event in (revenue[0], income[0]))))
            if not count:
                missing.append(security)
        windows.append(dict(window=window['window'], held_securities=len(held),
            securities_with_pairs=len({row['security_id'] for row in records}),
            securities_without_pairs=missing, pair_count=len(records),
            pairs_on_held_date=sum(row['baseline_held_on_acceptance_date'] for row in records),
            negative_pairs_on_held_date=sum(row['baseline_held_on_acceptance_date'] and
                row['both_absolute_changes_negative'] for row in records),
            original_verified_pairs=sum(row['original_verified_in_inventory'] for row in records),
            records=records))
    return dict(windows=windows, signal=False, limitations=[
        'Counts cover existing direct 10-Q candidates, not all expected quarterly reports.',
        'Same-date baseline holdings are a feasibility screen, not timestamp-safe execution exposure.',
        'Before-holding events and later portfolio branches are not evaluated here.',
        'SEC acceptance is not earliest news release. Negative changes are not earnings surprises.',
        'Original verification flags describe this inventory only, not separate review artifacts.',
        'No model inference, parameter search, price outcome evaluation or production change.'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory', type=Path, required=True)
    parser.add_argument('--queue', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = build(json.loads(args.inventory.read_bytes()), json.loads(args.queue.read_bytes()))
    result['inputs'] = {str(path): sha256(path.read_bytes()).hexdigest()
                        for path in (args.inventory, args.queue)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps([{key: value for key, value in row.items() if key != 'records'}
                      for row in result['windows']]))
