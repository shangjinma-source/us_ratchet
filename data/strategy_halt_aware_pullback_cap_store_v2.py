"""Isolated content-addressed cap evidence; budgets include unique blobs and metadata.

Every referenced blob is checked before replay. No deletion, legacy writes or
production activation. Complete legacy snapshots remain independently replayable.
"""
from contextlib import closing
from hashlib import sha256
from pathlib import Path
import json
import sqlite3
from data.strategy_halt_aware_pullback_cap_store_v1 import (
    PullbackCapStore as EmbeddedStore, encoded, replay_legacy)
from data.strategy_halt_aware_pullback_entry_v1 import VERSION, digest, require, stamp
from data.strategy_halt_aware_pullback_sources_v1 import ADAPTER_VERSION, candidate_from_yahoo_bytes


def blob_reference(raw):
    return dict(sha256=sha256(raw).hexdigest(), bytes=len(raw))


def read_blob(connection, reference):
    require(type(reference) is dict and set(reference)=={'sha256','bytes'}, 'CAP_BLOB_REFERENCE')
    require(type(reference['bytes']) is int and reference['bytes'] >= 0, 'CAP_BLOB_SIZE')
    row=connection.execute('SELECT byte_count,payload FROM cap_evidence_blobs WHERE digest=?',
                           (reference['sha256'],)).fetchone()
    require(row is not None, 'CAP_BLOB_MISSING')
    count, raw=row
    require(type(raw) is bytes and count==reference['bytes']==len(raw)
            and sha256(raw).hexdigest()==reference['sha256'], 'CAP_BLOB_CHANGED')
    return raw


def resolve_parameters(connection, stored):
    parameters=dict(stored)
    legacy_reference=parameters.pop('legacy_blob')
    halt_reference=parameters.pop('halt_blob')
    raw_reference=parameters.pop('raw_blob')
    raw=read_blob(connection,raw_reference)
    require(raw_reference['sha256']==parameters['expected_sha256'], 'CAP_RAW_REFERENCE_MISMATCH')
    snapshot=json.loads(read_blob(connection,legacy_reference))
    parameters['halt_raw']=read_blob(connection,halt_reference) if halt_reference is not None else None
    return raw, parameters, snapshot


class PullbackCapStore(EmbeddedStore):
    def __init__(self,path,*,clock,max_history_rows,max_history_bytes,legacy_path=None):
        require(callable(clock),'SERVER_CLOCK_REQUIRED')
        require(type(max_history_rows) is int and max_history_rows>0 and
                type(max_history_bytes) is int and max_history_bytes>0,'INVALID_HISTORY_BUDGET')
        self.path=str(path);self.clock=clock
        self.max_history_rows=max_history_rows;self.max_history_bytes=max_history_bytes
        self.legacy_path=Path(legacy_path).resolve() if legacy_path is not None else None
        require(self.legacy_path is None or self.legacy_path!=Path(path).resolve(),'LEGACY_PATH_COLLISION')
        with closing(sqlite3.connect(self.path)) as c,c:
            existing={row[0] for row in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            require(not existing or existing=={'cap_evidence_blobs','halt_cap_records_v2'},'CAP_V2_STORAGE_NOT_ISOLATED')
            c.execute('CREATE TABLE IF NOT EXISTS cap_evidence_blobs (digest TEXT PRIMARY KEY, byte_count INTEGER NOT NULL, payload BLOB NOT NULL)')
            c.execute('CREATE TABLE IF NOT EXISTS halt_cap_records_v2 (binding TEXT NOT NULL, ordinal INTEGER NOT NULL, parameters TEXT NOT NULL, result TEXT NOT NULL, previous_hash TEXT NOT NULL, record_hash TEXT NOT NULL, PRIMARY KEY(binding,ordinal))')

    def _budget(self,c):
        # Account for payload plus hashes/length metadata, not just raw source bytes.
        blobs=c.execute('SELECT COALESCE(SUM(LENGTH(payload)+LENGTH(digest)+8),0) FROM cap_evidence_blobs').fetchone()[0]
        records=c.execute('SELECT COALESCE(SUM(LENGTH(CAST(binding AS BLOB))+8+LENGTH(CAST(parameters AS BLOB))+LENGTH(CAST(result AS BLOB))+LENGTH(previous_hash)+LENGTH(record_hash)),0) FROM halt_cap_records_v2').fetchone()[0]
        require(blobs+records<=self.max_history_bytes,'CAP_HISTORY_BUDGET_EXCEEDED')
        return dict(unique_blob_bytes=blobs,chain_metadata_bytes=records,total_bytes=blobs+records)

    def _put(self,c,raw):
        reference=blob_reference(raw)
        c.execute('INSERT OR IGNORE INTO cap_evidence_blobs VALUES(?,?,?)',
                  (reference['sha256'],reference['bytes'],raw))
        require(read_blob(c,reference)==raw,'CAP_BLOB_CHANGED')
        return reference

    def candidate(self,*,raw,expected_sha256,security_id,ticker,session,session_open,session_close,
                  captured_at,checked_at,now,rebound_fraction,minimum_discount,maximum_age_seconds,
                  halt_raw=None,halt_receipt=None):
        begun=stamp(self.clock());require(begun>=stamp(now),'SERVER_CLOCK_BEFORE_REQUEST')
        parameters=dict(expected_sha256=expected_sha256,security_id=security_id,ticker=ticker,
            session=session,session_open=session_open,session_close=session_close,captured_at=captured_at,
            checked_at=checked_at,now=begun.isoformat(),rebound_fraction=rebound_fraction,
            minimum_discount=minimum_discount,maximum_age_seconds=maximum_age_seconds,halt_receipt=halt_receipt)
        initial=candidate_from_yahoo_bytes(raw=raw,halt_raw=halt_raw,previous_cap=None,**parameters)
        binding_object=initial['candidate']['binding'];binding=encoded(binding_object)
        snapshot=self._legacy_snapshot(binding_object)
        migrated,legacy_hash=replay_legacy(snapshot,binding_object,self.max_history_rows,self.max_history_bytes)
        snapshot_bytes=encoded(snapshot).encode()
        with closing(sqlite3.connect(self.path,timeout=30)) as c:
            try:
                # Acquire reader exclusion before validation; commit must not wait on a reader after the final clock check.
                c.execute('BEGIN EXCLUSIVE');self._budget(c)
                count=c.execute('SELECT COUNT(*) FROM halt_cap_records_v2 WHERE binding=?',(binding,)).fetchone()[0]
                require(count<self.max_history_rows,'CAP_HISTORY_BUDGET_EXCEEDED')
                stored=dict(parameters,raw_blob=blob_reference(raw),legacy_blob=blob_reference(snapshot_bytes),
                            halt_blob=blob_reference(halt_raw) if halt_raw is not None else None)
                self._budget(c)
                rows=c.execute('SELECT ordinal,parameters,result,previous_hash,record_hash FROM halt_cap_records_v2 WHERE binding=? ORDER BY ordinal',(binding,)).fetchall()
                previous_cap=migrated;previous_hash='';previous_time=stamp(migrated['observed_at']) if migrated else None
                for expected,row in enumerate(rows):
                    ordinal,arguments_json,result_json,parent,record_hash=row
                    require(ordinal==expected and parent==previous_hash,'CAP_HISTORY_CHAIN_MISMATCH')
                    arguments=json.loads(arguments_json)
                    historical_raw,decoded,historical_snapshot=resolve_parameters(c,arguments)
                    require(arguments['legacy_blob']==stored['legacy_blob'] and historical_snapshot==snapshot,'LEGACY_SNAPSHOT_CHANGED')
                    # Same verified snapshot hash across this transaction: legacy replay above covers every reference.
                    replay=candidate_from_yahoo_bytes(raw=historical_raw,previous_cap=previous_cap,**decoded)
                    require(encoded(replay['candidate']['binding'])==binding,'CAP_HISTORY_BINDING_MISMATCH')
                    observed=stamp(decoded['captured_at'])
                    require(previous_time is None or observed>previous_time,'CAP_HISTORY_TIME_REVERSED')
                    require(encoded(replay)==result_json,'CAP_HISTORY_REPLAY_MISMATCH')
                    computed=digest(dict(ordinal=ordinal,parameters=arguments,result=replay,previous_hash=parent))
                    require(computed==record_hash,'CAP_HISTORY_DIGEST_MISMATCH')
                    previous_cap=replay['candidate']['cap_declaration'];previous_hash=computed;previous_time=observed
                require(previous_time is None or stamp(captured_at)>previous_time,'CAP_INPUT_NOT_NEWER')
                result=candidate_from_yahoo_bytes(raw=raw,halt_raw=halt_raw,previous_cap=previous_cap,**parameters)
                self._put(c,raw);self._put(c,snapshot_bytes)
                if halt_raw is not None:self._put(c,halt_raw)
                ordinal=len(rows)
                record_hash=digest(dict(ordinal=ordinal,parameters=stored,result=result,previous_hash=previous_hash))
                c.execute('INSERT INTO halt_cap_records_v2 VALUES(?,?,?,?,?,?)',
                          (binding,ordinal,encoded(stored),encoded(result),previous_hash,record_hash))
                budget=self._budget(c)
                require(self._legacy_snapshot(binding_object)==snapshot,'LEGACY_CHANGED_BEFORE_COMMIT')
                final=stamp(self.clock());require(final>=begun,'SERVER_CLOCK_REVERSED')
                require(final<stamp(result['candidate']['reference_valid_until']),'CAP_REFERENCE_EXPIRED_BEFORE_COMMIT')
                c.commit()
                proof=dict(schema='HALT_AWARE_FROZEN_PULLBACK_PROOF_V2',kernel_version=VERSION,
                    adapter_version=ADAPTER_VERSION,parameters=stored,legacy_record_hash=legacy_hash,
                    raw_sha256=expected_sha256,prior_cap=previous_cap,prior_record_hash=previous_hash,
                    ordinal=ordinal,record_hash=record_hash,result=result,candidate_digest=digest(result['candidate']),
                    commit_checked_at=final.isoformat(),evidence_storage='CONTENT_ADDRESSED_SQLITE_V2')
                proof['proof_digest']=digest(proof)
                return dict(result,frozen_proof=proof,cap_store_receipt=dict(ordinal=ordinal,record_hash=record_hash,
                    prior_history_replayed=len(rows),budget=budget,orders_created=False,production_enabled=False,
                    checked_before_commit=final.isoformat()))
            except Exception:
                c.rollback();raise
