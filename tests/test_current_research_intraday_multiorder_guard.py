from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import patch
import sqlite3
import tempfile
import unittest
from data.current_research_intraday_execution import IntradayExecutionService
from test_current_research_intraday_execution import NOW, payload, snapshot
import test_current_research_intraday_multiorder_service as fixtures


class AtomicGuardTests(unittest.TestCase):
    def test_source_lock_held_through_sql_commit_then_attempt_proceeds(self):
        with tempfile.TemporaryDirectory() as root:
            service, before, clock, current, calls = fixtures.MultiorderServiceTests().fixture(root)
            reference = IntradayExecutionService(snapshot_reader=snapshot, fetch=lambda _:payload(), clock=lambda:NOW)
            service.acceptance_guard = lambda **_:reference.lock
            account = before['account_id']; proposal = service.preview(account,before['revision'])['proposal']
            commit_entered=Event(); permit_commit=Event(); attempted=Event()
            original_connect=sqlite3.connect
            class DelayedCommit(sqlite3.Connection):
                def commit(self):
                    commit_entered.set()
                    if not permit_commit.wait(5):raise RuntimeError('test commit gate timed out')
                    return super().commit()
            def connect(*args,**kwargs):
                return original_connect(*args,**dict(kwargs,factory=DelayedCommit))
            def quote_attempt():
                attempted.set()
                return reference.preview('a'*24)
            with ThreadPoolExecutor(max_workers=2) as pool:
                with patch('data.current_research_intraday_paper_store.sqlite3.connect',side_effect=connect):
                    accepted=pool.submit(service.accept,account,proposal['proposal_id'],'guarded',before['revision'])
                    self.assertTrue(commit_entered.wait(5))
                    quote=pool.submit(quote_attempt);self.assertTrue(attempted.wait(5))
                    self.assertEqual(reference.reference_attempt_sequence,0)
                    self.assertFalse(quote.done())
                    permit_commit.set()
                    accepted.result(10);quote.result(10)
            self.assertEqual(reference.reference_attempt_sequence,1)
            # No source access, including guard acquisition, on exact retry.
            service.acceptance_guard=lambda **_:self.fail('retry guard accessed')
            service.evidence_provider=lambda **_:self.fail('retry source accessed')
            self.assertEqual(service.accept(account,proposal['proposal_id'],'guarded',before['revision'])['status'],'ACCEPTED')

    def test_preceding_attempt_rejects_proposal_and_rollback_releases_guard(self):
        with tempfile.TemporaryDirectory() as root:
            service,before,clock,current,calls=fixtures.MultiorderServiceTests().fixture(root)
            reference=IntradayExecutionService(snapshot_reader=snapshot,fetch=lambda _:payload(),clock=lambda:NOW)
            account=before['account_id'];proposal=service.preview(account,before['revision'])['proposal']
            original_provider=service.evidence_provider
            service.acceptance_guard=lambda **_:reference.lock
            def current_provider(**kwargs):
                if reference.reference_attempt_sequence:raise ValueError('REFERENCE_CHANGED')
                return original_provider(**kwargs)
            service.evidence_provider=current_provider
            with ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(reference.preview,'a'*24).result(5)
            with self.assertRaisesRegex(ValueError,'REFERENCE_CHANGED'):
                service.accept(account,proposal['proposal_id'],'reject',before['revision'])
            self.assertEqual(service.store.read(account),before)
            with ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(reference.preview,'a'*24).result(5)
            self.assertEqual(reference.reference_attempt_sequence,2)

    def test_no_guard_cannot_accept_new_operation(self):
        with tempfile.TemporaryDirectory() as root:
            service,before,clock,current,calls=fixtures.MultiorderServiceTests().fixture(root)
            proposal=service.preview(before['account_id'],before['revision'])['proposal']
            service.acceptance_guard=None
            with self.assertRaisesRegex(ValueError,'ATOMIC_EVIDENCE_GUARD_REQUIRED'):
                service.accept(before['account_id'],proposal['proposal_id'],'unsafe',before['revision'])
            self.assertEqual(service.store.read(before['account_id']),before)


if __name__=='__main__':unittest.main()
