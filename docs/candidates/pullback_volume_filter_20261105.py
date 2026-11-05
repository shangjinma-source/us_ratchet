"""Research-only same-source contraction; no signal generation or account writes."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from backtest.research_exact_fraction_json import loads


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def apply_filter(signals, inventory, review_rows, actions):
    indexed = {}
    for row in review_rows:
        key = (row['security_id'], row['breakout'], row['confirmation'])
        require(key not in indexed, 'DUPLICATE_REVIEW_PAIR')
        indexed[key] = row
    result, audit, seen = deepcopy(signals), [], set()
    for day, block in signals.items():
        retained = []
        for entry in block['entries']:
            sid, start, end = entry['security_id'], entry['breakout_date'], entry['confirmation_date']
            require(start < end == day, 'SIGNAL_DATE_MISMATCH')
            key = (sid, start, end)
            require(key not in seen and key in indexed, 'MISSING_OR_DUPLICATE_SIGNAL_PAIR')
            seen.add(key)
            row = indexed[key]
            require(row['pairs'] and not row['source_conflict'], 'MISSING_OR_CONFLICTED_PAIR')
            for action in actions:
                if sid in (action.get('security_id'), action.get('new_security_id')):
                    require(not (start < action['date'] <= end), 'ACTION_CROSSES_VOLUME_PAIR')
            volumes = []
            source_rows = inventory['securities'][sid]['volume_by_source']
            actual_sources = {source for source, values in source_rows.items() if start in values and end in values}
            require(actual_sources == {pair['source'] for pair in row['pairs']}, 'PAIR_SOURCE_DOMAIN_MISMATCH')
            require(len(row['pairs']) == len(actual_sources), 'DUPLICATE_PAIR_SOURCE')
            for pair in row['pairs']:
                values = source_rows[pair['source']]
                a, b = values[start], values[end]
                require(type(a) is int and type(b) is int and a >= 0 and b >= 0, 'INVALID_VOLUME')
                require((a, b) == (pair['breakout_volume'], pair['confirmation_volume']), 'PAIR_VOLUME_MISMATCH')
                volumes.append((a, b))
            require(len(set(volumes)) == 1, 'SOURCE_VOLUME_CONFLICT')
            a, b = volumes[0]
            keep = b < a
            require(type(row['raw_contraction']) is bool and row['raw_contraction'] == keep, 'REVIEW_DECISION_MISMATCH')
            if keep:
                retained.append(deepcopy(entry))
            audit.append(dict(security_id=sid, breakout=start, confirmation=end,
                              breakout_volume=a, confirmation_volume=b, retained=keep,
                              reason='CONFIRMATION_VOLUME_LOWER' if keep else 'CONFIRMATION_VOLUME_NOT_LOWER',
                              sources=sorted(actual_sources)))
        result[day]['entries'] = retained
    require(seen == set(indexed), 'UNCONSUMED_REVIEW_PAIRS')
    return result, audit


def filter_volume_signals(*, root, window, signals_path, execution_inputs_path, review_path, expected_hashes):
    root = Path(root)
    verified = {}
    def read(path, expected, decode=False):
        raw = (root / path).read_bytes()
        require(sha256(raw).hexdigest() == expected, 'SOURCE_CHANGED:' + str(path))
        verified[str(path)] = expected
        return raw.decode('utf-8') if decode else raw
    review = json.loads(read(review_path, expected_hashes[review_path]))
    require(window in ('early', 'late'), 'UNKNOWN_WINDOW')
    inventory_path = 'tmp/pullback_volume_inventory_20261105_v3_final/' + window + '.json'
    for path in (signals_path, inventory_path):
        require(review['source_hashes'][path] == expected_hashes[path], 'INPUT_BINDING_MISMATCH')
    inventory = json.loads(read(inventory_path, expected_hashes[inventory_path]))
    signals = loads(read(signals_path, expected_hashes[signals_path]))
    document = loads(read(execution_inputs_path, expected_hashes[execution_inputs_path]))['document']
    for pins in (inventory['source_hashes'], document['source_hashes'], document.get('action_source_hashes', {})):
        for path, digest in pins.items():
            if path in verified:
                require(verified[path] == digest, 'SOURCE_PIN_CONFLICT')
            else:
                read(path, digest)
    actions = list(document['assembled']['actions']) + list(document['assembled'].get('provider_actions', []))
    for event in document.get('provider_event_inventory', []):
        if event['kind'] == 'splits':
            for sid, sources in document['assembled']['price_source_references'].items():
                if event['source'] in sources:
                    actions.append(dict(security_id=sid, date=event['date'], type='provider_split'))
    # Reject any mapped corporate action crossing a pair, including identity changes.
    output, rows = apply_filter(signals, inventory, review['windows'][window]['rows'], actions)
    return output, dict(scope='SAME_SOURCE_RAW_VOLUME_CONTRACTION_NOT_DOLLAR_VOLUME_OR_GLOBAL_UNIT_ADMISSION',
                        rows=rows, source_hashes=verified, retained=sum(r['retained'] for r in rows),
                        removed=sum(not r['retained'] for r in rows))
