"""Bounded issuer-calendar collection; no account, model, or trading writes."""
from contextlib import closing
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from core.news_investment_review_v1 import require, moment
from data.news_issuer_source import capture
from data.news_refresh_service import NewsRefreshService
from data.news_scheduled_earnings_v1 import build_scheduled_earnings


class ScheduledEarningsService:
    def __init__(self, cache, *, collector=capture, clock=None):
        self.cache = Path(cache)
        self.collector = collector
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        # Reuse transactional cross-process ownership and 4/day, 10-minute limits.
        # Only our bounded collector runs; the default model runner is never used.
        self.refresh = NewsRefreshService(self.cache, runner=self._collect, clock=self.clock)

    def _collect(self):
        result = self.collector(self.cache, now=self.clock())
        require(result['request_count'] <= 3, 'SCHEDULE_REQUEST_LIMIT')
        snapshot = dict(generated_at=self.clock().isoformat(), events=result['events'],
                        source_receipts=result['receipts'], fetch_errors=result['errors'])
        self.cache.mkdir(parents=True, exist_ok=True)
        temporary = self.cache/('snapshot-'+uuid4().hex+'.tmp')
        try:
            temporary.write_text(json.dumps(snapshot, ensure_ascii=False), encoding='utf-8')
            temporary.replace(self.cache/'snapshot.json')
        finally:
            temporary.unlink(missing_ok=True)
        return not snapshot['fetch_errors']

    def start(self):
        code, value = self.refresh.start()
        return code, dict(status=value['status'], refresh_id=value.get('id'),
                          model_called=False, account_mutated=False)

    def read(self):
        base = dict(events=[], calendar_coverage_complete=False, changes_strategy=False,
                    model_called=False, account_mutated=False, supported_tickers=['MRNA'])
        path = self.cache/'snapshot.json'
        if not path.exists():
            return dict(base, status='NO_CAPTURE')
        try:
            require(self.progress()['status'] not in {'FAILED', 'UNCONFIRMED'},
                    'SCHEDULE_LATEST_REFRESH_UNCONFIRMED')
            raw = path.read_bytes()
            require(len(raw) <= 2_000_000, 'SCHEDULE_SNAPSHOT_TOO_LARGE')
            snapshot = json.loads(raw)
            require(not snapshot['fetch_errors'], 'SCHEDULE_CAPTURE_INCOMPLETE')
            current = self.clock()
            require(moment(snapshot['generated_at']) <= current, 'SCHEDULE_FUTURE_CAPTURE')
            # Rebuild from receipts at read time, so elapsed calls and changed raw
            # bodies cannot survive in a cached precomputed calendar.
            snapshot['generated_at'] = current.isoformat()
            result = build_scheduled_earnings(snapshot, self.cache,
                [dict(ticker='MRNA', security_id='issuer:MRNA')])
            return dict(base, **{k: result[k] for k in ('status', 'events', 'coverage')},
                        checked_at=current.isoformat(), snapshot_sha256=sha256(raw).hexdigest())
        except (ValueError, KeyError, TypeError, OSError) as error:
            return dict(base, status='UNAVAILABLE', reason=str(error)[:120])

    def progress(self):
        """Read only: no refresh lease mutation or new collector on polling."""
        path = self.cache/'refresh_requests_v2.sqlite3'
        if not path.exists():
            return dict(status='IDLE')
        with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True)) as database:
            values = [json.loads(row[0]) for row in database.execute('SELECT document FROM jobs')]
        if not values:
            return dict(status='IDLE')
        latest = max(values, key=lambda value: moment(value['started_at']))
        status = latest['status']
        if status == 'RUNNING' and (self.clock()-moment(latest['started_at'])).total_seconds() > 600:
            status = 'UNCONFIRMED'
        return dict(status=status, refresh_id=latest['id'])
