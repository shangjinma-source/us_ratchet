from copy import deepcopy
from datetime import datetime
from hashlib import sha256
from pathlib import Path
import json
import multiprocessing
import os
import sqlite3
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from core.strategy_account_ledger import canonical
from backtest.current_strategy_prospective_paper_store_v1 import ProspectivePaperStore, SOURCE
import test_current_strategy_prospective_paper_book_v1 as fixture


def crash_worker(root, authority, decisions, request, phase):
    def fault(at):
        if at == phase:
            os._exit(77)
    store = ProspectivePaperStore(root=root, authority=authority,
        admission_loader=lambda:dict(decisions=decisions, settlements={}),
        target_reader=lambda:'independently-reviewed-target',
        clock=lambda:datetime.fromisoformat('2026-10-30T14:00:10+00:00'), fault=fault)
    store.apply(request)


class ProspectiveStoreTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.f = fixture.ProspectiveBookTests(); self.f.setUp()
        a = self.f.authority
        arguments = a['descriptor_arguments']
        source = (Path(__file__).resolve().parents[1]/SOURCE).read_bytes()
        arguments['code_bytes'][SOURCE] = source
        app = json.loads(arguments['descriptor_bytes'])
        app['code_sha256'][SOURCE] = sha256(source).hexdigest()
        arguments['descriptor_bytes'] = canonical(app)
        hashed = sha256(arguments['descriptor_bytes']).hexdigest()
        arguments['trusted_descriptor_sha256'] = hashed
        approval = json.loads(arguments['approval_bytes']); approval['descriptor_sha256'] = hashed
        arguments['approval_bytes'] = canonical(approval)
        arguments['trusted_approval_sha256'] = sha256(arguments['approval_bytes']).hexdigest()
        registration = json.loads(a['registration_bytes']); registration['descriptor_sha256'] = hashed
        a['registration_bytes'] = canonical(registration)
        a['trusted_registration_sha256'] = sha256(a['registration_bytes']).hexdigest()
        self.now = '2026-10-30T14:00:00+00:00'
        self.target = 'independently-reviewed-target'
        self.store = self.make()
        self.book = self.store.initialize()

    def make(self, **kwargs):
        return ProspectivePaperStore(root=self.directory.name, authority=self.f.authority,
            admission_loader=lambda:dict(decisions=self.f.admitted, settlements=self.f.settlements),
            target_reader=lambda:self.target, clock=lambda:datetime.fromisoformat(self.now), **kwargs)

    def request(self):
        return dict(kind='ACCEPT', operation_id='accepted', expected_revision=self.book['revision'],
                    decision_bytes=self.f.decision(self.book))

    def test_request_byte_budget_rejects_before_lock(self):
        before = self.store.path.read_bytes()
        # Non-ASCII text exercises bytes, rather than Python character count.
        with patch('backtest.current_strategy_prospective_paper_store_v1.MAX_BYTES', 1024):
            with patch.object(self.store, '_write') as writer:
                with self.assertRaisesRegex(ValueError, 'PROSPECTIVE_REQUEST_BUDGET'):
                    self.store.apply({'payload': '\u4e2d' * 400})
                writer.assert_not_called()
        self.assertEqual(self.store.path.read_bytes(), before)
        self.assertEqual(self.store.read(), self.book)

    def test_target_changed_during_final_source_check_rolls_back(self):
        import backtest.current_strategy_prospective_paper_store_v1 as storage
        request = self.request()
        self.now = '2026-10-30T14:00:10+00:00'
        original = storage._context

        def change_target(*args, **kwargs):
            result = original(*args, **kwargs)
            self.target = 'new-monthly-target'
            return result

        with patch.object(storage, '_context', side_effect=change_target):
            with self.assertRaisesRegex(ValueError, 'PROSPECTIVE_CURRENT_TARGET_CHANGED'):
                self.store.apply(request)
        self.assertEqual(self.store.read(), self.book)

    def test_restart_accept_settle_and_idempotent_read_after_window(self):
        request=self.request();self.now='2026-10-30T14:00:10+00:00'
        accepted=self.store.apply(request)
        self.assertEqual(self.make().read(),accepted)
        oid=next(iter(accepted['orders']))
        bar=dict(security_id='A',start='2026-10-30T14:01:00+00:00',end='2026-10-30T14:02:00+00:00',
                 open='100',high='101',low='99',close='100')
        settle=self.f.settlement_request(accepted,'settle',{oid:[bar]},'2026-10-30T14:02:00+00:00')
        self.now='2026-10-30T14:02:01+00:00'
        filled=self.make().apply(settle)
        self.assertEqual(filled['shares'],{'A':10})
        self.assertEqual(self.make().apply(settle),filled)
        self.assertEqual(self.make().read(),filled)
        self.f.admitted.clear()
        with self.assertRaisesRegex(ValueError,'NOT_SERVER_ADMITTED'):self.make().read()

    def test_lock_wait_crosses_window_and_rolls_back(self):
        request=self.request();self.now='2026-10-30T14:00:59+00:00'
        connection=sqlite3.connect(self.store.path)
        connection.execute('BEGIN');connection.execute('SELECT * FROM prospective_header').fetchall()
        started=threading.Event();errors=[]
        def write():
            started.set()
            try:self.make().apply(request)
            except Exception as exc:errors.append(str(exc))
        worker=threading.Thread(target=write);worker.start();started.wait();time.sleep(.1)
        self.now='2026-10-30T14:01:01+00:00'
        connection.rollback();connection.close();worker.join(5)
        self.assertFalse(worker.is_alive());self.assertTrue(errors)
        self.assertEqual(self.store.read(),self.book)

    def test_final_commit_clock_or_target_change_rolls_back(self):
        request=self.request();self.now='2026-10-30T14:00:10+00:00'
        def late(phase):
            if phase=='before_commit':self.now='2026-10-30T14:01:00+00:00'
        with self.assertRaisesRegex(ValueError,'COMMIT_ACCEPT_DEADLINE'):self.make(fault=late).apply(request)
        self.assertEqual(self.store.read(),self.book)
        self.now='2026-10-30T14:00:10+00:00'
        def target(phase):
            if phase=='before_commit':self.target='changed'
        with self.assertRaisesRegex(ValueError,'CURRENT_TARGET_CHANGED'):self.make(fault=target).apply(request)
        self.assertEqual(self.store.read(),self.book)

    def test_real_process_crash_before_and_after_commit(self):
        request=self.request()
        for phase, expected in [('after_insert',0),('before_commit',0),('after_commit',1)]:
            process=multiprocessing.get_context('spawn').Process(target=crash_worker,
                args=(self.directory.name,self.f.authority,self.f.admitted,request,phase))
            process.start();process.join(15)
            self.assertFalse(process.is_alive());self.assertEqual(process.exitcode,77)
            recovered=self.make().read()
            self.assertEqual(len(recovered['operations']),expected)
        self.now='2026-10-30T21:00:00+00:00'
        self.assertEqual(self.make().apply(request),recovered)

    def test_corruption_and_hardlink_rejected(self):
        with tempfile.TemporaryDirectory() as other:
            link=Path(other)/'alias.sqlite3';os.link(self.store.path,link)
            try:
                with self.assertRaisesRegex(ValueError,'LINK_PATH'):self.store.read()
            finally:link.unlink()
        with sqlite3.connect(self.store.path) as connection:
            connection.execute("UPDATE prospective_header SET count=1")
        connection.close()
        with self.assertRaisesRegex(ValueError,'BUDGET_OR_COUNT'):self.store.read()

    def test_concurrent_same_request_is_once_and_conflict_is_rejected(self):
        request=self.request();self.now='2026-10-30T14:00:10+00:00'
        results=[];errors=[]
        def write(value):
            try:results.append(self.make().apply(value))
            except Exception as exc:errors.append(str(exc))
        workers=[threading.Thread(target=write,args=(request,)) for _ in range(2)]
        for worker in workers:worker.start()
        for worker in workers:worker.join(5)
        self.assertEqual(errors,[]);self.assertEqual(len(results),2)
        self.assertEqual(results[0],results[1]);self.assertEqual(len(self.store.read()['operations']),1)
        different=deepcopy(request);different['operation_id']='other'
        with self.assertRaisesRegex(ValueError,'STALE_REVISION'):self.make().apply(different)

    def test_final_clock_rollback_rejects_even_inside_window(self):
        request=self.request();self.now='2026-10-30T14:00:10+00:00'
        store=self.make()
        ticks=iter(datetime.fromisoformat('2026-10-30T14:00:'+value+'+00:00')
                   for value in ('10','11','12','13','12'))
        store.clock=lambda:next(ticks)
        with self.assertRaisesRegex(ValueError,'CLOCK_ROLLBACK'):store.apply(request)
        self.assertEqual(self.store.read(),self.book)


if __name__=='__main__':unittest.main()
