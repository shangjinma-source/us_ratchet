"""Candidate public observation journal. Transactional writes; read-only bounded GET.

Deploy beside news_evidence_groups.py in data/. No legacy raw-file reconstruction.
"""
from contextlib import closing
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3

from data.news_evidence_groups import group_evidence

DATABASE = 'observations_v1.sqlite3'
FIELDS = ('id', 'title', 'url', 'source', 'source_type', 'published_at',
          'published_raw', 'collected_at', 'tickers', 'relevance', 'source_text',
          'content_kind', 'content_sha256', 'issuer_source_chain', 'noise_hint')


def append_observations(cache, events):
    """Call once before URL deduplication, before AI. Failure aborts refresh.

    Complete batch commits atomically; retrying identical input is idempotent.
    Capture times remain unchanged. recorded_at is only the journal write time.
    """
    events = list(events)
    if len(events) > 250:
        raise ValueError('OBSERVATION_BATCH_LIMIT')
    observations = []
    for event in events:
        if not isinstance(event, dict):
            raise ValueError('OBSERVATION_OBJECT_REQUIRED')
        row = {key: event[key] for key in FIELDS if key in event}
        row['source_uncertainty'] = event.get('source_uncertainty', event.get('uncertainty', []))
        stamp = datetime.fromisoformat(row['collected_at'])
        if stamp.utcoffset() is None:
            raise ValueError('AWARE_CAPTURE_TIME_REQUIRED')
        observations.append(row)
    payload = json.dumps(observations, ensure_ascii=False, sort_keys=True,
                         separators=(',', ':'), allow_nan=False)
    encoded = payload.encode('utf-8')
    if len(encoded) > 2_000_000:
        raise ValueError('OBSERVATION_BYTE_LIMIT')
    batch_id = sha256(encoded).hexdigest()
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(cache / DATABASE, timeout=5)) as connection, connection:
        connection.execute('PRAGMA synchronous=FULL')
        connection.execute('CREATE TABLE IF NOT EXISTS batches '
                           '(sequence INTEGER PRIMARY KEY, batch_id TEXT UNIQUE NOT NULL, '
                           'recorded_at TEXT NOT NULL, payload TEXT NOT NULL)')
        connection.execute('INSERT OR IGNORE INTO batches(batch_id, recorded_at, payload) VALUES (?,?,?)',
                           (batch_id, datetime.now(timezone.utc).isoformat(), payload))
    return dict(batch_id=batch_id, observations=len(observations))


def read_history(cache, *, batch_limit=16, event_limit=500):
    """No writes, network or collection; latest bounded batches only.

    Persisted journal is retained. Read limits never delete history. Corruption
    raises rather than silently returning an apparently complete empty history.
    """
    if not 1 <= batch_limit <= 32 or not 1 <= event_limit <= 1000:
        raise ValueError('BOUNDED_HISTORY_REQUIRED')
    path = Path(cache) / DATABASE
    if not path.exists():
        return dict(status='NO_RECORDED_HISTORY', batches=[], truncated=False,
                    scope='local recorded observations only',
                    time_semantics='recorded_at is journal write time, not first availability',
                    coverage='truncated only describes this local read, never complete news coverage',
                    evidence=group_evidence([]))
    with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=5)) as connection:
        rows = connection.execute('SELECT batch_id,recorded_at,payload FROM batches '
                                  'ORDER BY sequence DESC LIMIT ?', (batch_limit + 1,)).fetchall()
    truncated = len(rows) > batch_limit
    observations, receipts = [], []
    for batch_id, recorded_at, payload in rows[:batch_limit]:
        raw = payload.encode('utf-8')
        if len(raw) > 2_000_000 or sha256(raw).hexdigest() != batch_id:
            raise ValueError('OBSERVATION_INTEGRITY_ERROR')
        batch = json.loads(payload)
        if not isinstance(batch, list) or len(batch) > 250:
            raise ValueError('OBSERVATION_BATCH_INVALID')
        available = event_limit - len(observations)
        chosen = batch[:available]
        start = len(observations)
        observations.extend(chosen)
        receipts.append(dict(batch_id=batch_id, recorded_at=recorded_at,
                             observation_indices=list(range(start, len(observations))),
                             recorded_observations=len(batch)))
        if len(chosen) < len(batch):
            truncated = True
        if len(observations) >= event_limit:
            truncated = truncated or len(receipts) < min(len(rows), batch_limit)
            break
    return dict(status='RECORDED_HISTORY', batches=receipts, truncated=truncated,
                scope='local recorded observations only',
                time_semantics='recorded_at is journal write time, not first availability',
                coverage='truncated only describes this local read, never complete news coverage',
                ordering='newest recorded batch first; original order within batch',
                evidence=group_evidence(observations))
