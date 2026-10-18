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

from data.strategy_account_live_pullback_entry import VERSION, digest, require, stamp
from data.strategy_account_live_pullback_sources import ADAPTER_VERSION, candidate_from_yahoo_bytes


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'))


class PullbackCapStore:
    def __init__(self, path, *, clock, max_history_rows, max_history_bytes):
        require(callable(clock), 'SERVER_CLOCK_REQUIRED')
        require(type(max_history_rows) is int and max_history_rows > 0
                and type(max_history_bytes) is int and max_history_bytes > 0,
                'INVALID_HISTORY_BUDGET')
        self.path = str(path)
        self.clock = clock
        self.max_history_rows = max_history_rows
        self.max_history_bytes = max_history_bytes
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute('''CREATE TABLE IF NOT EXISTS pullback_caps (
                binding TEXT NOT NULL, ordinal INTEGER NOT NULL, raw BLOB NOT NULL,
                parameters TEXT NOT NULL, result TEXT NOT NULL, previous_hash TEXT NOT NULL,
                record_hash TEXT NOT NULL, PRIMARY KEY(binding, ordinal))''')

    def candidate(self, *, raw, expected_sha256, security_id, ticker, session,
                  session_open, session_close, captured_at, checked_at, now,
                  rebound_fraction, minimum_discount, maximum_age_seconds):
        started_at = stamp(self.clock())
        require(started_at >= stamp(now), 'SERVER_CLOCK_BEFORE_REQUEST')
        parameters = dict(expected_sha256=expected_sha256, security_id=security_id,
            ticker=ticker, session=session, session_open=session_open,
            session_close=session_close, captured_at=captured_at, checked_at=checked_at,
            now=started_at.isoformat(), rebound_fraction=rebound_fraction, minimum_discount=minimum_discount,
            maximum_age_seconds=maximum_age_seconds)
        # Validate before opening a transaction; no caller-supplied cap is accepted.
        initial = candidate_from_yahoo_bytes(raw=raw, previous_cap=None, **parameters)
        binding = encoded(initial['candidate']['binding'])
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
            previous_cap, previous_hash, previous_time = None, '', None
            for expected_ordinal, row in enumerate(rows):
                ordinal, stored_raw, stored_parameters, stored_result, parent, record_hash = row
                require(ordinal == expected_ordinal and parent == previous_hash,
                        'CAP_HISTORY_CHAIN_MISMATCH')
                arguments = json.loads(stored_parameters)
                replay = candidate_from_yahoo_bytes(raw=stored_raw, previous_cap=previous_cap,
                                                    **arguments)
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
            result = candidate_from_yahoo_bytes(raw=raw, previous_cap=previous_cap, **parameters)
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
            final_now = stamp(self.clock())
            require(final_now >= started_at, 'SERVER_CLOCK_REVERSED')
            require(final_now < stamp(result['candidate']['reference_valid_until']),
                    'CAP_REFERENCE_EXPIRED_BEFORE_COMMIT')
            connection.commit()
            proof = dict(schema='V2_FROZEN_PULLBACK_PROOF_V1', kernel_version=VERSION,
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
