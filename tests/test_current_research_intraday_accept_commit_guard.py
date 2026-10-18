from concurrent.futures import ThreadPoolExecutor
from threading import Event
import tempfile
import unittest
import test_current_research_intraday_paper_service as fixtures


class CommitGuardTests(unittest.TestCase):
    def test_initial_source_guard_spans_commit_and_rollback(self):
        for fail_commit in (False, True):
            with self.subTest(fail_commit=fail_commit), tempfile.TemporaryDirectory() as root:
                service, reference, _ = fixtures.ServiceTests().fixture(root)
                proposal = service.preview('a'*24)['proposal']
                original_connect = service.store._connect
                commit_entered, release_commit, refresh_started, snapshot_read = (Event() for _ in range(4))
                original_snapshot = reference.snapshot_reader
                def snapshot(rid):
                    snapshot_read.set()
                    return original_snapshot(rid)
                reference.snapshot_reader = snapshot
                class ConnectionProxy:
                    def __init__(self, connection): self.connection = connection
                    def __getattr__(self, name): return getattr(self.connection, name)
                    def commit(self):
                        commit_entered.set()
                        if not release_commit.wait(5): raise RuntimeError('test commit timeout')
                        if fail_commit: raise RuntimeError('injected commit failure')
                        self.connection.commit()
                service.store._connect = lambda **kw: ConnectionProxy(original_connect(**kw))
                def refresh():
                    refresh_started.set()
                    return reference.preview('a'*24)
                with ThreadPoolExecutor(max_workers=2) as pool:
                    accepted = pool.submit(service.accept, 'a'*24, proposal['proposal_id'], 'guard-test')
                    self.assertTrue(commit_entered.wait(5))
                    refreshed = pool.submit(refresh)
                    try:
                        self.assertTrue(refresh_started.wait(5))
                        self.assertFalse(snapshot_read.wait(.1), 'quote attempt crossed pre-commit guard')
                    finally:
                        release_commit.set()
                    if fail_commit:
                        with self.assertRaisesRegex(RuntimeError, 'injected commit failure'): accepted.result(5)
                    else: self.assertEqual(accepted.result(5)['cash'], '20000')
                    refreshed.result(5)
                    self.assertTrue(snapshot_read.is_set())
                service.store._connect = original_connect
                if fail_commit:
                    with self.assertRaisesRegex(ValueError, 'ACCOUNT_NOT_FOUND'): service.account('a'*24)
                else: self.assertEqual(service.account('a'*24)['cash'], '20000')


if __name__ == '__main__': unittest.main()
