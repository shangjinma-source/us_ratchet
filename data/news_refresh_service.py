"""Transactional daily budget and process-owned refresh lease."""
from contextlib import closing
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
from threading import Thread, Lock
from uuid import uuid4
from zoneinfo import ZoneInfo

_active = set()
_active_lock = Lock()
LEASE_SECONDS = 600


def process_identity():
    import psutil
    return os.getpid(), psutil.Process().create_time()


def owner_alive(pid, created):
    import psutil
    try:
        return psutil.Process(pid).create_time() == created
    except psutil.NoSuchProcess:
        return False
    # AccessDenied is uncertainty, never permission to launch another worker.


def stamp(value):
    result = datetime.fromisoformat(value)
    if result.utcoffset() is None:
        raise ValueError('AWARE_TIME_REQUIRED')
    return result


class NewsRefreshService:
    def __init__(self, cache, *, runner=None, clock=None):
        self.cache = Path(cache)
        self.runner = runner or self._run
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _connect(self):
        self.cache.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.cache/'refresh_requests_v2.sqlite3', timeout=5)
        connection.execute('PRAGMA synchronous=FULL')
        connection.execute('CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, document TEXT NOT NULL)')
        connection.execute('CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY)')
        connection.commit()
        return connection

    def _migrate(self, connection):
        if connection.execute("SELECT 1 FROM metadata WHERE key='legacy_imported'").fetchone():
            return
        for path in sorted((self.cache/'requests').glob('*.json')):
            if path.stat().st_size > 65536:
                raise ValueError('RECEIPT_TOO_LARGE')
            value = json.loads(path.read_bytes())
            started = stamp(value['started_at'])
            if value.get('status') == 'RUNNING':
                raise ValueError('LEGACY_WORKER_STATUS_UNRESOLVED')
            row = dict(id='legacy:'+path.name, started_at=started.isoformat(),
                       status=value.get('status') if value.get('status') in ('SUCCEEDED','FAILED') else 'FAILED', finished_at=value.get('finished_at'),
                       message='历史更新记录；保留预算。', legacy_running=value.get('status') == 'RUNNING')
            connection.execute('INSERT OR IGNORE INTO jobs VALUES (?,?)',
                               (row['id'], json.dumps(row)))
        connection.execute("INSERT INTO metadata VALUES ('legacy_imported')")

    @staticmethod
    def _save(connection, row):
        connection.execute('INSERT OR REPLACE INTO jobs VALUES (?,?)',
                           (row['id'], json.dumps(row, ensure_ascii=False)))

    def _rows(self, connection, now):
        self._migrate(connection)
        rows = [json.loads(row[0]) for row in connection.execute('SELECT document FROM jobs')]
        for row in rows:
            age = (now-stamp(row['started_at'])).total_seconds()
            if age < 0:
                raise ValueError('CLOCK_REVERSED')
            if row['status'] != 'RUNNING':
                continue
            alive = owner_alive(row['worker_pid'], row['worker_created_at'])
            if row['worker_pid'] == os.getpid():
                with _active_lock:
                    alive = alive and row['id'] in _active
            if not alive and age >= LEASE_SECONDS:
                row.update(status='FAILED', finished_at=now.isoformat(), message='原更新进程已结束；保留本次预算。')
                self._save(connection, row)
        return rows

    def status(self):
        try:
            now = stamp(self.clock().isoformat())
            with closing(self._connect()) as connection, connection:
                connection.execute('BEGIN IMMEDIATE')
                rows = self._rows(connection, now)
            return max(rows, key=lambda row: stamp(row['started_at'])) if rows else dict(status='IDLE', message='尚未启动新闻更新。')
        except Exception:
            return dict(status='FAILED', message='更新记录无法核验，禁止新采集。')

    def start(self):
        job = None
        try:
            now = stamp(self.clock().isoformat())
            pid, created = process_identity()
            with closing(self._connect()) as connection, connection:
                connection.execute('BEGIN IMMEDIATE')
                rows = self._rows(connection, now)
                running = [r for r in rows if r['status'] == 'RUNNING' or
                           (r.get('legacy_running') and (now-stamp(r['started_at'])).total_seconds() < LEASE_SECONDS)]
                if running:
                    return 409, dict(running[-1])
                today = now.astimezone(ZoneInfo('Asia/Shanghai')).date()
                if sum(stamp(r['started_at']).astimezone(ZoneInfo('Asia/Shanghai')).date() == today for r in rows) >= 4:
                    return 429, dict(status='FAILED', message='今日4次分析预算已用完，仍可读取已保存结果。')
                if any((now-stamp(r['started_at'])).total_seconds() < 600 for r in rows):
                    return 429, dict(status='FAILED', message='两次采集分析至少间隔10分钟。')
                job = dict(status='RUNNING', message='正在采集官方来源并分析最多4条事件。',
                           started_at=now.isoformat(), finished_at=None, id=uuid4().hex,
                           worker_pid=pid, worker_created_at=created, lease_seconds=LEASE_SECONDS)
                self._save(connection, job)
                with _active_lock:
                    _active.add(job['id'])
            self.worker = Thread(target=self._complete, args=(job,), daemon=True, name='bounded-news-refresh')
            try:
                self.worker.start()
            except Exception:
                self._finish(job, False)
                raise
            return 202, dict(job)
        except Exception:
            if job:
                with _active_lock:
                    _active.discard(job['id'])
            return 503, dict(status='FAILED', message='更新记录或运行状态无法核验，未启动新采集。')

    def _run(self):
        from data.news_desk import collect, analyze, save_snapshot
        snapshot = collect(self.cache, limit=20)
        from data.news_model_coordinator_v1 import ModelCoordinator
        with ModelCoordinator(self.cache).reserve('refresh', units=4):
            snapshot = analyze(snapshot, self.cache, limit=4, timeout=180)
        save_snapshot(snapshot, self.cache)
        return snapshot.get('analysis_summary', {}).get('status') in ('ANALYZED', 'CACHED')

    def _finish(self, job, success):
        try:
            row = dict(job, status='SUCCEEDED' if success else 'FAILED',
                       message='新闻已更新，可查看分析与原文依据。' if success else '本次更新未完成，请查看已保存结果。',
                       finished_at=self.clock().isoformat())
            with closing(self._connect()) as connection, connection:
                connection.execute('BEGIN IMMEDIATE')
                self._save(connection, row)
        finally:
            with _active_lock:
                _active.discard(job['id'])

    def _complete(self, job):
        try:
            success = bool(self.runner())
        except Exception:
            success = False
        self._finish(job, success)
