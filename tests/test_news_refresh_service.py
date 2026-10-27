from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import unittest
from data.news_refresh_service import NewsRefreshService

class RefreshTests(unittest.TestCase):
    def test_single_flight_and_persistent_cooldown(self):
        with TemporaryDirectory() as folder:
            entered, finish = Event(), Event()
            def runner():
                entered.set()
                finish.wait(3)
                return True
            service = NewsRefreshService(folder, runner=runner)
            self.assertEqual(service.start()[0], 202)
            self.assertTrue(entered.wait(1))
            self.assertEqual(service.start()[0], 409)
            restored = NewsRefreshService(folder, runner=lambda: self.fail('must not run'))
            self.assertEqual(restored.start()[0], 409)
            finish.set()
            service.worker.join(2)
            self.assertEqual(service.status()['status'], 'SUCCEEDED')

    def test_daily_budget_survives_restart(self):
        with TemporaryDirectory() as folder:
            now = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)
            history = Path(folder) / 'requests'
            history.mkdir()
            for i in range(4):
                (history / f'{i}.json').write_text(json.dumps(dict(started_at=(now-timedelta(hours=i+1)).isoformat())))
            service = NewsRefreshService(folder, clock=lambda: now, runner=lambda: self.fail('budget must prevent call'))
            self.assertEqual(service.start()[0], 429)

if __name__ == '__main__':
    unittest.main()
