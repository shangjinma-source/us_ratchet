"""Offline original inline-XBRL check; does not create a trading signal."""
from __future__ import annotations

import argparse
from collections import Counter
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from pathlib import Path

from bs4 import BeautifulSoup

CONCEPTS = {
    'Revenues', 'RevenueFromContractWithCustomerExcludingAssessedTax', 'NetIncomeLoss',
}


def local_name(tag):
    return tag.name.lower().split(':')[-1] if tag.name else ''


def child_text(tag, name):
    child = tag.find(lambda item: local_name(item) == name)
    return child.get_text(strip=True) if child else None


def review(facts, filing_bytes, accession):
    soup = BeautifulSoup(filing_bytes, 'html.parser')
    contexts = {}
    for context in soup.find_all(lambda item: local_name(item) == 'context'):
        # Companyfacts covers the entity, not segment/dimension-specific facts.
        if context.find(lambda item: local_name(item) in ('segment', 'scenario')):
            continue
        contexts[context.get('id')] = (
            child_text(context, 'startdate'), child_text(context, 'enddate'))
    units = {}
    for unit in soup.find_all(lambda item: local_name(item) == 'unit'):
        measures = unit.find_all(lambda item: local_name(item) == 'measure')
        if len(measures) == 1 and measures[0].get_text(strip=True) == 'iso4217:USD':
            units[unit.get('id')] = 'USD'
    original = {}
    unsupported = 0
    for item in soup.find_all(lambda node: local_name(node) == 'nonfraction'):
        name = item.get('name', '')
        if name not in {'us-gaap:' + concept for concept in CONCEPTS}:
            continue
        period = contexts.get(item.get('contextref'))
        if not period or item.get('unitref') not in units:
            continue
        # Do not guess arbitrary inline-XBRL transformations.
        transform = item.get('format', '').split(':')[-1].lower()
        if transform not in ('', 'num-dot-decimal', 'numdotdecimal'):
            unsupported += 1
            continue
        text = item.get_text('', strip=True).replace(',', '').replace('\u00a0', '')
        try:
            value = Decimal(text) * Decimal(10) ** int(item.get('scale', '0'))
            if item.get('sign') == '-':
                value = -value
            if not value.is_finite():
                raise InvalidOperation
        except (InvalidOperation, ValueError):
            unsupported += 1
            continue
        key = (name.split(':')[1], *period)
        original.setdefault(key, set()).add(value)
    checks = []
    seen = set()
    for concept in sorted(CONCEPTS):
        rows = facts.get('facts', {}).get('us-gaap', {}).get(concept, {}).get('units', {}).get('USD', [])
        for row in rows:
            if row.get('accn') != accession or not row.get('start'):
                continue
            key = (concept, row['start'], row['end'])
            value = Decimal(str(row['val']))
            if (*key, value) in seen:
                continue
            seen.add((*key, value))
            values = original.get(key, set())
            state = 'MATCH' if values == {value} else ('ORIGINAL_MISSING' if not values else 'CONFLICT')
            checks.append(dict(concept=concept, start=row['start'], end=row['end'],
                               api_value=str(value), original_values=sorted(map(str, values)), status=state))
    counts = dict(Counter(row['status'] for row in checks))
    return dict(status='MATCHED_SELECTED_FACTS' if checks and counts == {'MATCH': len(checks)} else 'INCOMPLETE_OR_CONFLICT',
                accession=accession, checks=checks, counts=counts,
                unsupported_original_values=unsupported,
                limitation='Selected numeric facts only; not original narrative, earliest release time, economic validation or a trading signal.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--facts', type=Path, required=True)
    parser.add_argument('--filing', type=Path, required=True)
    parser.add_argument('--accession', required=True)
    parser.add_argument('--output', type=Path, required=True)
    arguments = parser.parse_args()
    raw_facts, raw_filing = arguments.facts.read_bytes(), arguments.filing.read_bytes()
    result = review(json.loads(raw_facts), raw_filing, arguments.accession)
    result['source_hashes'] = {str(arguments.facts): sha256(raw_facts).hexdigest(),
                               str(arguments.filing): sha256(raw_filing).hexdigest()}
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({key: result[key] for key in ('status', 'counts', 'unsupported_original_values')}))


if __name__ == '__main__':
    main()
