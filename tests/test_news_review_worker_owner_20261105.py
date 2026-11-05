"""Real service start/run/thread completion; no model or account mutations."""
from datetime import datetime, timezone
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Thread
import unittest
from data.news_investment_service_v1 import NewsInvestmentService
from docs.candidates.news_review_worker_owner_20261105 import ReviewWorkerOwner


class Tests(unittest.TestCase):
    def test_close_racing_admitted_start_waits_for_registration(self):
        with TemporaryDirectory() as folder:
            entered, release = Event(), Event()
            def validate():
                entered.set()
                release.wait(5)
            service = NewsInvestmentService(cache=Path(folder), validate=validate,
                context=lambda: ({'revision': 'r'}, {'target_id': 't', 'proposal_id': 'p'}, {}),
                preview=lambda **kwargs: {'status': 'WAIT'}, collector=lambda *a, **k: {'events': []})
            owner = ReviewWorkerOwner(service)
            binding = dict(expected_revision='r', target_id='t', expected_proposal_id='p')
            responses = []
            caller = Thread(target=lambda: responses.append(service.start(binding)))
            caller.start()
            try:
                self.assertTrue(entered.wait(2))
                self.assertEqual(owner.close_and_wait(timeout=0)['stage'], 'START')
            finally:
                release.set()
                caller.join(2)
                drained = owner.close_and_wait(timeout=2)
            self.assertFalse(caller.is_alive())
            self.assertEqual(responses[0][0], 202)
            self.assertEqual(len(owner.workers), 1)
            self.assertEqual(drained['status'], 'REVIEWS_DRAINED')
            with self.assertRaisesRegex(ValueError, 'REVIEW_SERVICE_CLOSING'):
                service.start(binding)

    def test_http_return_does_not_mean_review_finished(self):
        with TemporaryDirectory() as folder:
            entered, release = Event(), Event()
            def collect(*args, **kwargs):
                entered.set()
                release.wait(5)
                return {'events': []}
            def preview(**kwargs):
                raise ValueError('CONTROLLED_PREVIEW_UNAVAILABLE')
            service = NewsInvestmentService(cache=Path(folder),
                context=lambda: ({'revision': 'r'}, {'target_id': 't', 'proposal_id': 'p'}, {}),
                preview=preview, collector=collect, clock=lambda: datetime.now(timezone.utc))
            owner = ReviewWorkerOwner(service)
            binding = dict(expected_revision='r', target_id='t', expected_proposal_id='p')
            try:
                code, job = service.start(binding)
                self.assertEqual(code, 202)
                self.assertTrue(entered.wait(2))
                self.assertEqual(service.status(job['job_id'])['status'], 'RUNNING')
                blocked = owner.close_and_wait(timeout=0)
                self.assertEqual(blocked['status'], 'REVIEW_DRAIN_TIMEOUT')
                self.assertEqual(blocked['alive'], 1)
                with self.assertRaisesRegex(ValueError, 'REVIEW_SERVICE_CLOSING'):
                    service.start(binding)
                with closing(service.connection()) as connection:
                    self.assertEqual(connection.execute('SELECT COUNT(*) FROM jobs').fetchone()[0], 1)
            finally:
                release.set()
                drained = owner.close_and_wait(timeout=2)
            self.assertEqual(drained['status'], 'REVIEWS_DRAINED')
            self.assertFalse(drained['may_switch'])
            self.assertFalse(any(worker.is_alive() for worker in owner.workers))
            self.assertEqual(service.status(job['job_id'])['status'], 'FAILED')


if __name__ == '__main__':
    unittest.main()
