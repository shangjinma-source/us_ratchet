"""Pure local cap-prefix replay; caller must authenticate the archive's provenance.

Hashes detect inconsistent records, not an adversarial rewrite of a whole chain.
No filesystem, live database, current clock, fetching or execution authority.
"""
import json
from hashlib import sha256
from data.current_quantity_v2_pullback_entry import digest, stamp
from data.current_quantity_v2_pullback_sources import candidate_from_yahoo_bytes

ARCHIVE_PATH = 'tmp/pullback_history_archive_replay_20261016_v1/chain.json'
ARCHIVE_SHA256 = '577060cff2a2833c35ebea76dcf67a9308f3381e888bc05f187b0a20eefaf136'


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def verify_chain(raw, record_hash, quote_raw, pullback, *, observed_at=None):
    require(type(raw) is bytes and len(raw) <= 32 * 1024 * 1024, 'PULLBACK_CHAIN_SIZE')
    document = json.loads(raw)
    require(document.get('schema') == 'LOCAL_PULLBACK_CHAIN_EXPORT_V1', 'PULLBACK_CHAIN_SCHEMA')
    rows = document['rows']
    require(type(rows) is list and 0 < len(rows) <= 4096, 'PULLBACK_CHAIN_SIZE')
    targets = [row for row in rows if row['record_hash'] == record_hash]
    require(len(targets) == 1, 'PULLBACK_CHAIN_TARGET_MISSING')
    target = targets[0]
    prefix = [row for row in rows if row['binding'] == target['binding'] and row['ordinal'] <= target['ordinal']]
    prefix.sort(key=lambda row: row['ordinal'])
    prior, parent, previous_time = None, '', None
    for ordinal, row in enumerate(prefix):
        require(type(row['ordinal']) is int and row['ordinal'] == ordinal and row['previous_hash'] == parent,
                'PULLBACK_CHAIN_SEQUENCE')
        parameters = row['parameters']
        payload = bytes.fromhex(row['raw_hex'])
        replay = candidate_from_yahoo_bytes(raw=payload, previous_cap=prior, **parameters)
        require(replay == row['result'] and replay['candidate']['binding'] == row['binding'], 'PULLBACK_CHAIN_REPLAY')
        require(digest(dict(ordinal=ordinal, parameters=parameters, result=replay, previous_hash=parent)) == row['record_hash'],
                'PULLBACK_CHAIN_RECORD_HASH')
        captured = stamp(parameters['captured_at'])
        require(previous_time is None or captured > previous_time, 'PULLBACK_CHAIN_TIME')
        if row['record_hash'] == record_hash:
            if observed_at is not None:
                require(stamp(parameters['now']) <= stamp(observed_at), 'PULLBACK_CHAIN_AFTER_OBSERVATION')
            require(payload == quote_raw and parameters['expected_sha256'] == sha256(quote_raw).hexdigest(),
                    'PULLBACK_CHAIN_QUOTE_MISMATCH')
            require(pullback == dict(replay['candidate'], prior_cap=prior, cap_record_hash=record_hash,
                    status='EXPERIMENTAL_NOT_PERFORMANCE_VALIDATED'), 'PULLBACK_CHAIN_REFERENCE_MISMATCH')
            return replay['candidate']
        prior, parent, previous_time = replay['candidate']['cap_declaration'], row['record_hash'], captured
    raise ValueError('PULLBACK_CHAIN_TARGET_MISSING')
