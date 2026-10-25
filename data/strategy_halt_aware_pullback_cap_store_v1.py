"""Isolated halt-aware cap chain with fully replayed read-only legacy ceiling migration.

Source snapshots are embedded in each row for standalone replay and count toward
the history budget. Legacy mutation after migration fails closed. No deployment.
"""
"""Live V2 adapter fork: original capture controls bars; checked clock permits at most 1s vendor lead. Old research module remains frozen."""
"""Offline research cap history, owned by the caller's server, never an order DB.

Every update replays stored raw bytes and parameters through the source adapter.
This detects inconsistent local records, not a malicious rewrite of the whole DB
or rollback by truncating a valid history tail. Limits bound complete history
replay; exceeding a limit refuses the update without pruning or skipping history.
"""
from contextlib import closing
import json
import sqlite3
from pathlib import Path
from data.strategy_account_live_pullback_sources import candidate_from_yahoo_bytes as legacy_candidate

from data.strategy_halt_aware_pullback_entry_v1 import VERSION, digest, require, stamp
from data.strategy_halt_aware_pullback_sources_v1 import ADAPTER_VERSION, candidate_from_yahoo_bytes


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'))


def decoded_parameters(parameters):
    args = dict(parameters)
    args.pop('legacy_snapshot')
    halt_hex = args.pop('halt_raw_hex')
    args['halt_raw'] = bytes.fromhex(halt_hex) if halt_hex is not None else None
    return args


def replay_legacy(snapshot, binding, max_rows, max_bytes):
    require(type(snapshot) is list and len(snapshot) <= max_rows, 'LEGACY_HISTORY_BUDGET')
    require(len(encoded(snapshot).encode()) <= max_bytes, 'LEGACY_HISTORY_BUDGET')
    prior, parent, observed = None, '', None
    for expected, row in enumerate(snapshot):
        require(row['ordinal'] == expected and row['previous_hash'] == parent, 'LEGACY_CHAIN_MISMATCH')
        arguments = row['parameters']
        result = legacy_candidate(raw=bytes.fromhex(row['raw_hex']), previous_cap=prior, **arguments)
        legacy_binding = result['candidate']['binding']
        require(all(legacy_binding[key] == value for key, value in binding.items() if key != 'policy_id'),
                'LEGACY_BINDING_MISMATCH')
        require(result == row['result'], 'LEGACY_REPLAY_MISMATCH')
        observed_new = stamp(arguments['captured_at'])
        require(observed is None or observed_new > observed, 'LEGACY_TIME_REVERSED')
        computed = digest(dict(ordinal=expected, parameters=arguments, result=result, previous_hash=parent))
        require(computed == row['record_hash'], 'LEGACY_DIGEST_MISMATCH')
        prior, parent, observed = result['candidate']['cap_declaration'], computed, observed_new
    migrated = dict(prior, binding=binding) if prior is not None else None
    return migrated, parent


class PullbackCapStore:
    def __init__(self, path, *, clock, max_history_rows, max_history_bytes, legacy_path=None):
        require(callable(clock), 'SERVER_CLOCK_REQUIRED')
        require(type(max_history_rows) is int and max_history_rows > 0
                and type(max_history_bytes) is int and max_history_bytes > 0,
                'INVALID_HISTORY_BUDGET')
        self.path = str(path)
        self.legacy_path = Path(legacy_path).resolve() if legacy_path is not None else None
        require(self.legacy_path is None or self.legacy_path != Path(path).resolve(), "LEGACY_PATH_COLLISION")
        self.clock = clock
        self.max_history_rows = max_history_rows
        self.max_history_bytes = max_history_bytes
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute('''CREATE TABLE IF NOT EXISTS pullback_caps (
                binding TEXT NOT NULL, ordinal INTEGER NOT NULL, raw BLOB NOT NULL,
                parameters TEXT NOT NULL, result TEXT NOT NULL, previous_hash TEXT NOT NULL,
                record_hash TEXT NOT NULL, PRIMARY KEY(binding, ordinal))''')

    def _legacy_snapshot(self, binding):
        if self.legacy_path is None:
            return []
        require(self.legacy_path.is_file(), 'LEGACY_STORE_MISSING')
        with closing(sqlite3.connect(self.legacy_path.as_uri()+'?mode=ro', uri=True)) as connection:
            candidates = connection.execute('SELECT DISTINCT binding FROM pullback_caps').fetchall()
            matches = [key for (key,) in candidates if all(json.loads(key).get(k) == v
                       for k,v in binding.items() if k != 'policy_id')]
            require(len(matches) <= 1, 'LEGACY_MULTIPLE_BINDINGS')
            if not matches:
                return []
            count, size = connection.execute('SELECT COUNT(*), COALESCE(SUM(LENGTH(raw)*2+LENGTH(parameters)+LENGTH(result)),0) FROM pullback_caps WHERE binding=?', (matches[0],)).fetchone()
            require(count <= self.max_history_rows and size <= self.max_history_bytes, 'LEGACY_HISTORY_BUDGET')
            rows = connection.execute('SELECT ordinal,raw,parameters,result,previous_hash,record_hash FROM pullback_caps WHERE binding=? ORDER BY ordinal', (matches[0],)).fetchall()
        return [dict(ordinal=o, raw_hex=bytes(r).hex(), parameters=json.loads(p), result=json.loads(v),
                     previous_hash=h, record_hash=d) for o,r,p,v,h,d in rows]

    def candidate(self, *, raw, expected_sha256, security_id, ticker, session,
                  session_open, session_close, captured_at, checked_at, now,
                  rebound_fraction, minimum_discount, maximum_age_seconds, halt_raw=None, halt_receipt=None):
        started_at = stamp(self.clock())
        require(started_at >= stamp(now), 'SERVER_CLOCK_BEFORE_REQUEST')
        parameters = dict(expected_sha256=expected_sha256, security_id=security_id,
            ticker=ticker, session=session, session_open=session_open,
            session_close=session_close, captured_at=captured_at, checked_at=checked_at,
            now=started_at.isoformat(), rebound_fraction=rebound_fraction, minimum_discount=minimum_discount,
            maximum_age_seconds=maximum_age_seconds)
        # Validate before opening a transaction; no caller-supplied cap is accepted.
        initial = candidate_from_yahoo_bytes(raw=raw, previous_cap=None, halt_raw=halt_raw, halt_receipt=halt_receipt, **parameters)
        binding_object = initial['candidate']['binding']
        binding = encoded(binding_object)
        snapshot = self._legacy_snapshot(binding_object)
        migrated_cap, legacy_hash = replay_legacy(snapshot, binding_object, self.max_history_rows, self.max_history_bytes)
        parameters.update(halt_raw_hex=halt_raw.hex() if halt_raw is not None else None,
                          halt_receipt=halt_receipt, legacy_snapshot=snapshot)
        connection = sqlite3.connect(self.path, timeout=30)
        try:
            connection.execute('BEGIN IMMEDIATE')
            count, history_bytes = connection.execute('''SELECT COUNT(*), COALESCE(SUM(
                LENGTH(raw)+LENGTH(CAST(parameters AS BLOB))+LENGTH(CAST(result AS BLOB))),0)
                FROM pullback_caps WHERE binding=?''', (binding,)).fetchone()
            require(count < self.max_history_rows and history_bytes <= self.max_history_bytes,
                    'CAP_HISTORY_BUDGET_EXCEEDED')
            rows = connection.execute('''SELECT ordinal,raw,parameters,result,
                previous_hash,record_hash FROM pullback_caps WHERE binding=?
                ORDER BY ordinal''', (binding,)).fetchall()
            previous_cap, previous_hash, previous_time = migrated_cap, '', stamp(migrated_cap['observed_at']) if migrated_cap else None
            for expected_ordinal, row in enumerate(rows):
                ordinal, stored_raw, stored_parameters, stored_result, parent, record_hash = row
                require(ordinal == expected_ordinal and parent == previous_hash,
                        'CAP_HISTORY_CHAIN_MISMATCH')
                arguments = json.loads(stored_parameters)
                require(arguments['legacy_snapshot'] == snapshot, 'LEGACY_SNAPSHOT_CHANGED')
                replay_legacy(arguments['legacy_snapshot'], binding_object, self.max_history_rows, self.max_history_bytes)
                replay = candidate_from_yahoo_bytes(raw=stored_raw, previous_cap=previous_cap,
                                                    **decoded_parameters(arguments))
                require(encoded(replay['candidate']['binding']) == binding,
                        'CAP_HISTORY_BINDING_MISMATCH')
                observed = stamp(arguments['captured_at'])
                require(previous_time is None or observed > previous_time,
                        'CAP_HISTORY_TIME_REVERSED')
                require(encoded(replay) == stored_result, 'CAP_HISTORY_REPLAY_MISMATCH')
                computed = digest(dict(ordinal=ordinal, parameters=arguments,
                    result=replay, previous_hash=previous_hash))
                require(computed == record_hash, 'CAP_HISTORY_DIGEST_MISMATCH')
                previous_cap = replay['candidate']['cap_declaration']
                previous_hash, previous_time = computed, observed
            require(previous_time is None or stamp(captured_at) > previous_time,
                    'CAP_INPUT_NOT_NEWER')
            result = candidate_from_yahoo_bytes(raw=raw, previous_cap=previous_cap, **decoded_parameters(parameters))
            ordinal = len(rows)
            record_hash = digest(dict(ordinal=ordinal, parameters=parameters,
                result=result, previous_hash=previous_hash))
            saved_parameters, saved_result = encoded(parameters), encoded(result)
            payload_bytes = len(raw) + len(saved_parameters.encode()) + len(saved_result.encode())
            require(history_bytes + payload_bytes <= self.max_history_bytes,
                    'CAP_HISTORY_BUDGET_EXCEEDED')
            connection.execute('INSERT INTO pullback_caps VALUES(?,?,?,?,?,?,?)',
                (binding, ordinal, raw, saved_parameters, saved_result, previous_hash, record_hash))
            # Covers lock wait, complete history replay, serialization and insertion.
            # The server-owned clock is read again immediately before commit.
            require(self._legacy_snapshot(binding_object) == snapshot, 'LEGACY_CHANGED_BEFORE_COMMIT')
            final_now = stamp(self.clock())
            require(final_now >= started_at, 'SERVER_CLOCK_REVERSED')
            require(final_now < stamp(result['candidate']['reference_valid_until']),
                    'CAP_REFERENCE_EXPIRED_BEFORE_COMMIT')
            connection.commit()
            proof = dict(schema='HALT_AWARE_FROZEN_PULLBACK_PROOF_V1', legacy_record_hash=legacy_hash, kernel_version=VERSION,
                adapter_version=ADAPTER_VERSION, policy=result['candidate']['policy'],
                raw_sha256=expected_sha256, parameters=parameters, prior_cap=previous_cap,
                prior_record_hash=previous_hash, ordinal=ordinal, record_hash=record_hash,
                candidate_digest=digest(result['candidate']), result=result,
                commit_checked_at=final_now.isoformat())
            proof['proof_digest'] = digest(proof)
            return dict(result, frozen_proof=proof, cap_store_receipt=dict(ordinal=ordinal,
                record_hash=record_hash, prior_history_replayed=len(rows),
                research_only=True, production_enabled=False, orders_created=False,
                external_authentication=False, checked_before_commit=final_now.isoformat()))
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
