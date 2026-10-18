"""Bind reviewed distribution semantics without changing any prices or targets."""
import argparse
from copy import deepcopy
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backtest.return_priority_monthly_execution_inputs_v4 import assemble_monthly_execution_inputs_v4

PREVIOUS = 'tmp/next12_execution_prepare_20261014_v2/prepared.json'
BINDING = 'tmp/next12_distribution_execution_binding_20261015_v1/binding.json'
OUTPUT = ROOT / 'tmp/next12_execution_prepare_20261014_v3'
REFRESHABLE_CODE = {
    'backtest/return_priority_limit_book_v4.py',
    'backtest/return_priority_monthly_quantity_provider_v4.py',
    'backtest/return_priority_ads_conversion.py',
    'backtest/return_priority_monthly_execution_inputs_v4.py',
    'tests/test_return_priority_ads_conversion.py',
}


def prepare(review_receipt):
    pins = {}
    history = []

    def read(path, expected=None, historical_container=None):
        path = Path(path)
        if not path.is_absolute():
            path = ROOT / path
        key = path.relative_to(ROOT).as_posix()
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if expected and expected != digest:
            if key not in REFRESHABLE_CODE or historical_container is None:
                raise ValueError('SOURCE_CHANGED:' + key)
            history.append(dict(path=key, historical_sha256=expected,
                                historical_container=historical_container,
                                current_direct_sha256=digest,
                                reason='ROOT_AUTHORIZED_REVIEWED_EXECUTION_CODE_UPDATE'))
        if key in pins and pins[key] != digest:
            raise ValueError('PIN_CONFLICT:' + key)
        pins[key] = digest
        return raw

    def document(path):
        result = json.loads(read(path))
        for source, digest in result.get('source_hashes', {}).items():
            read(source, digest, historical_container=path)
        return result

    old = document(PREVIOUS)
    binding = document(BINDING)
    read(review_receipt)
    read('tmp/next12_dtc_independent_20261015_v2.json', '0ae7fa3ff4c639fdcef8a57122b2e5f5159ff15b6067f0f499feda5d8e6b265f')
    read('scripts/return_priority_next12_execution_v3.py')
    for path in REFRESHABLE_CODE:
        read(path)
    result = deepcopy(old)
    bindings = {event['event_id']: event for event in binding['events']}
    if len(bindings) != 3 or set(bindings) != {e['event_id'] for e in old['distribution_events']}:
        raise ValueError('DISTRIBUTION_DOMAIN_MISMATCH')
    for event in result['distribution_events']:
        admitted = bindings[event['event_id']]
        for field in ('effective_date', 'parent_sid', 'post_parent_sid', 'child_sid'):
            if event[field] != admitted[field]:
                raise ValueError('DISTRIBUTION_IDENTITY_MISMATCH:' + field)
        if event.get('child_delivery_confirmed') is not False or admitted['child_delivery_confirmed'] is not False:
            raise ValueError('UNSUPPORTED_CHILD_DELIVERY_CHANGE')
        for flag in ('eligibility_confirmed', 'ordered_steps_confirmed', 'parent_delivered_units_confirmed'):
            if admitted[flag] is not True:
                raise ValueError('UNCONFIRMED_DISTRIBUTION_FLAG')
            event[flag] = admitted[flag]
        event['source_references'] = sorted(set(event['source_references'] + admitted['source_references'] + [BINDING]))
        if any(ref not in pins for ref in event['source_references']):
            raise ValueError('UNPINNED_DISTRIBUTION_BINDING')
        event['execution_confirmation_scope'] = binding['model']
        event['execution_confirmation_evidence'] = admitted['evidence']

    result['source_hashes'] = pins
    result['historical_code_pin_transitions'] = history
    result['historical_evidence_pin_policy'] = (
        'Historical JSON bytes and their internal old code hashes are preserved. '
        'Only the explicit execution-code allowlist may be superseded; current '
        'source_hashes bind executable bytes. All other mismatches fail closed.')
    result['distribution_binding_review_receipt'] = str(review_receipt)
    result['status'] = 'PREPARED_CONDITIONAL_DISTRIBUTION_BINDINGS_REVIEWED'
    for field in ('ohlc', 'windows', 'session_dates', 'metadata', 'source_provenance',
                  'supported_conversions', 'conversion_unresolved', 'conversion_limitations',
                  'distribution_fractional_cash_values'):
        if result[field] != old[field]:
            raise ValueError('PROTECTED_DATA_CHANGED:' + field)
    for before, after in zip(old['distribution_events'], result['distribution_events']):
        for field in ('blockers', 'child_delivery_confirmed', 'fractional_cash_values',
                      'child_ratio', 'parent_ratio', 'timing', 'ordered_steps'):
            if before[field] != after[field]:
                raise ValueError('UNKNOWN_OR_ACTION_CHANGED:' + field)
    assembled = assemble_monthly_execution_inputs_v4(result)
    count = 0
    for window in result['windows']:
        for sid, cost in window['search_arguments']['prices'].items():
            if Fraction(cost) != Fraction(result['ohlc'][sid][window['decision_date']]['close']):
                raise ValueError('DECISION_PRICE_CHANGED')
            count += 1
    summary = dict(status='V3_PURE_ASSEMBLY_PASS', source_pins=len(pins),
                   protected_data_unchanged=True, child_delivery_confirmed=False,
                   exact_decision_costs=count, monthly_inputs=len(assembled['monthly_inputs']),
                   historical_code_pin_transitions=history, search_calls=0, book_calls=0)
    return result, summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--review-receipt', required=True)
    args = parser.parse_args()
    if OUTPUT.exists():
        raise ValueError('CREATE_ONLY_OUTPUT_EXISTS')
    result, summary = prepare(args.review_receipt)
    OUTPUT.mkdir()
    for name, payload in [('prepared.json', result), ('assembly_readback.json', summary)]:
        with (OUTPUT / name).open('x', encoding='utf-8') as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2, allow_nan=False)
    print(json.dumps(dict(path=str(OUTPUT / 'prepared.json'),
                          sha256=hashlib.sha256((OUTPUT / 'prepared.json').read_bytes()).hexdigest(),
                          **summary)))
