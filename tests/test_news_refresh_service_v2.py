from contextlib import closing
import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from threading import Event
from concurrent.futures import ThreadPoolExecutor
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('news_refresh_candidate', Path(__file__).resolve().parents[1]/'docs/candidates/news_refresh_service.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
Service = module.NewsRefreshService


class RefreshTests(unittest.TestCase):
    def test_concurrent_instances_and_alive_owner_past_lease(self):
        with TemporaryDirectory() as folder:
            now = [datetime(2026, 10, 27, 1, tzinfo=timezone.utc)]
            finish = Event()
            services = [Service(folder, runner=lambda: finish.wait(5), clock=lambda: now[0]) for _ in range(2)]
            try:
                with ThreadPoolExecutor(2) as pool:
                    results = list(pool.map(lambda s: s.start()[0], services))
                self.assertEqual(sorted(results), [202, 409])
                now[0] += timedelta(minutes=20)
                self.assertEqual(Service(folder, clock=lambda: now[0]).start()[0], 409)
            finally:
                finish.set()
                for service in services:
                    if hasattr(service, 'worker'): service.worker.join(2)
            self.assertEqual(Service(folder, clock=lambda: now[0]).status()['status'], 'SUCCEEDED')

    def test_failed_job_retains_budget_and_restart_cooldown(self):
        with TemporaryDirectory() as folder:
            def fail(): raise RuntimeError('test')
            service = Service(folder, runner=fail)
            self.assertEqual(service.start()[0], 202)
            service.worker.join(2)
            self.assertEqual(Service(folder).status()['status'], 'FAILED')
            self.assertEqual(Service(folder).start()[0], 429)

    def test_dead_owner_lease_recovery(self):
        with TemporaryDirectory() as folder:
            now = datetime(2026, 10, 27, 1, tzinfo=timezone.utc)
            service = Service(folder, runner=lambda: True, clock=lambda: now)
            with closing(service._connect()) as db, db:
                db.execute("INSERT INTO metadata VALUES ('legacy_imported')")
                job = dict(id='dead', status='RUNNING', started_at=(now-timedelta(seconds=599)).isoformat(), worker_pid=123, worker_created_at=0)
                service._save(db, job)
            with patch.object(module, 'owner_alive', return_value=False):
                self.assertEqual(service.start()[0], 409)
                service.clock = lambda: now+timedelta(seconds=1)
                self.assertEqual(service.start()[0], 202)
                service.worker.join(2)
            with closing(sqlite3.connect(Path(folder)/'refresh_requests_v2.sqlite3')) as db:
                old = json.loads(db.execute("SELECT document FROM jobs WHERE id='dead'").fetchone()[0])
                self.assertEqual(old['status'], 'FAILED')

    def test_legacy_import_once_and_beijing_daily_budget(self):
        with TemporaryDirectory() as folder:
            now = datetime(2026, 10, 26, 17, tzinfo=timezone.utc)
            history = Path(folder)/'requests'; history.mkdir()
            for i in range(4):
                (history/f'{i}.json').write_text(json.dumps(dict(started_at=(now-timedelta(minutes=10*(i+1))).isoformat(), status='FAILED')))
            service = Service(folder, clock=lambda: now)
            self.assertEqual(service.start()[0], 429)
            self.assertEqual(Service(folder, clock=lambda: now).start()[0], 429)
            with closing(sqlite3.connect(Path(folder)/'refresh_requests_v2.sqlite3')) as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0], 4)

    def test_bad_or_running_legacy_receipt_blocks_without_partial_migration(self):
        for value in ('{broken', json.dumps(dict(started_at='2026-10-27T00:00:00+00:00', status='RUNNING'))):
            with TemporaryDirectory() as folder:
                history = Path(folder)/'requests'; history.mkdir(); (history/'job.json').write_text(value)
                service = Service(folder, runner=lambda: self.fail('must not launch'))
                self.assertEqual(service.start()[0], 503)
                with closing(sqlite3.connect(Path(folder)/'refresh_requests_v2.sqlite3')) as db:
                    self.assertEqual(db.execute('SELECT COUNT(*) FROM metadata').fetchone()[0], 0)


if __name__ == '__main__': unittest.main()
