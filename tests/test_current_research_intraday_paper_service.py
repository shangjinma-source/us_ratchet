from copy import deepcopy
from datetime import timedelta
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest

from data.current_research_intraday_execution import IntradayExecutionService
from data.current_research_intraday_journal import IntradayObservationJournal
from data.current_research_intraday_paper_service import IntradayPaperService
from test_current_research_intraday_execution import NOW, payload, snapshot


class ServiceTests(unittest.TestCase):
    def test_new_pending_or_failed_snapshot_blocks_old_initial_preview(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Event
        with tempfile.TemporaryDirectory() as directory:
            service, reference, _ = self.fixture(directory)
            service.continuity_reader = lambda **_: self.fail('initial cash must not need continuity review')
            proposal = service.preview('a'*24)['proposal']
            started, release = Event(), Event()
            def slow_fetch(_):
                started.set()
                if not release.wait(5): raise RuntimeError('test release timed out')
                return payload()
            reference.fetch = slow_fetch
            with ThreadPoolExecutor(max_workers=1) as pool:
                refresh = pool.submit(reference.preview, 'a'*24)
                self.assertTrue(started.wait(5))
                try:
                    with self.assertRaisesRegex(ValueError,'CURRENT_REFERENCE_UNAVAILABLE'):
                        service.accept('a'*24, proposal['proposal_id'], 'must-not-accept')
                finally:
                    release.set()
                refresh.result(5)
            with self.assertRaisesRegex(ValueError,'ACCOUNT_NOT_FOUND'):
                service.account('a'*24)
            proposal = service.preview('a'*24)['proposal']
            reference.snapshot_reader = lambda _: (_ for _ in ()).throw(ValueError('snapshot unavailable'))
            with self.assertRaisesRegex(ValueError,'snapshot unavailable'): reference.preview('a'*24)
            with self.assertRaisesRegex(ValueError,'CURRENT_REFERENCE_UNAVAILABLE'):
                service.accept('a'*24, proposal['proposal_id'], 'failed-snapshot')
            reference.snapshot_reader = snapshot
            proposal = service.preview('a'*24)['proposal']
            accepted = service.accept('a'*24, proposal['proposal_id'], 'fresh-initial')
            self.assertEqual(accepted['cash'],'20000')

    def fixture(self, directory):
        root = Path(directory)
        (root/'source.json').write_bytes(b'{}')
        pins = {'source.json':sha256(b'{}').hexdigest()}
        calendar = dict(schema='SCHEDULED_REGULAR_SESSIONS_V1', source_hashes=pins, calendar=['2026-10-15'],
                        sessions=[dict(date='2026-10-15',timezone='America/New_York',
                                       open_at='2026-10-15T09:30:00-04:00',close_at='2026-10-15T16:00:00-04:00')])
        (root/'calendar.json').write_text(json.dumps(calendar), encoding='utf-8')
        pins['calendar.json'] = sha256((root/'calendar.json').read_bytes()).hexdigest()
        clock = [NOW]
        reference = IntradayExecutionService(snapshot_reader=snapshot, fetch=lambda _:payload(), clock=lambda:clock[0],
                                             journal=IntradayObservationJournal(root/'journal'))
        service = IntradayPaperService(root=root, directory=root/'store', reference_service=reference,
                                      snapshot_reader=snapshot, clock=lambda:clock[0],
                                      calendar_config=dict(calendar_path='calendar.json',calendar_source_hashes=pins))
        return service, reference, clock

    def test_preview_does_not_create_account_and_retry_survives_expiry(self):
        with tempfile.TemporaryDirectory() as directory:
            service, _, clock = self.fixture(directory)
            proposal = service.preview('a'*24)['proposal']
            self.assertFalse((Path(directory)/'store').exists())
            state = service.accept('a'*24, proposal['proposal_id'], 'op')
            clock[0] += timedelta(minutes=5)
            service.proposals.clear()
            self.assertEqual(service.accept('a'*24, proposal['proposal_id'], 'op'), state)
            with self.assertRaises(ValueError): service.accept('a'*24, proposal['proposal_id'], 'another-op')

    def test_refresh_or_expiry_rejects_new_acceptance(self):
        for refresh in (False, True):
            with tempfile.TemporaryDirectory() as directory:
                service, reference, clock = self.fixture(directory)
                proposal = service.preview('a'*24)['proposal']
                if refresh: reference.preview('a'*24)
                else: clock[0] += timedelta(minutes=3)
                with self.assertRaises(ValueError): service.accept('a'*24, proposal['proposal_id'], 'op')

    def test_server_recording_time_and_idempotent_fill(self):
        with tempfile.TemporaryDirectory() as directory:
            service, _, clock = self.fixture(directory)
            proposal = service.preview('a'*24)['proposal']
            state = service.accept('a'*24, proposal['proposal_id'], 'op')
            clock[0] += timedelta(minutes=5)
            event = dict(event_id='fill',kind='FILL',expected_revision=state['revision'],order_id=state['order']['order_id'],
                         quantity=1,price='1400',fees='1',executed_at=(NOW+timedelta(minutes=4)).isoformat())
            with self.assertRaisesRegex(ValueError, 'SERVER_OWNED'):
                service.record_event('a'*24,dict(event,recorded_at=NOW.isoformat()))
            after = service.record_event('a'*24,event)
            self.assertEqual(after['cash'],'18599')
            self.assertEqual(after['events'][0]['recorded_at'],clock[0].isoformat())
            clock[0] += timedelta(minutes=1)
            self.assertEqual(service.record_event('a'*24,event),after)

    def test_existing_account_restores_without_new_quote_or_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            service, reference, clock = self.fixture(directory)
            proposal = service.preview('a'*24)['proposal']
            state = service.accept('a'*24, proposal['proposal_id'], 'op')
            reference.fetch = lambda _: self.fail('Restore must not request another quote')
            service.snapshot = lambda _: self.fail('Restore must use persisted acceptance lineage')
            clock[0] += timedelta(days=1)
            restored = service.preview('a'*24)
            self.assertEqual(restored['status'],'EXISTING_ACCOUNT')
            self.assertEqual(restored['state'],state)
            self.assertIsNone(restored['proposal'])


if __name__ == '__main__': unittest.main()
