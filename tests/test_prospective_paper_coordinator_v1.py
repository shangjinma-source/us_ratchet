from copy import deepcopy
from datetime import datetime
import sqlite3
import threading
import time
from tempfile import TemporaryDirectory
import unittest
import json
from unittest.mock import patch
from core.strategy_account_ledger import canonical

from backtest.current_strategy_prospective_paper_coordinator_v1 import ProspectivePaperCoordinator,SOURCE
from backtest.current_strategy_prospective_paper_store_v1 import SOURCE as STORE_SOURCE
from data.strategy_prospective_paper_selection_v1 import select_prospective_target,verify_prospective_target
from data.strategy_prospective_paper_decision_v1 import produce_prospective_decision
from test_strategy_prospective_paper_integration_v1 import fixture,execution
import test_strategy_prospective_paper_integration_v1 as integration


class CoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        original=integration.setup
        def calendar_with_later_session(path):
            value=original(path);calendar=json.loads(value['calendar_bytes'])
            calendar['sessions'].append(dict(date='2026-11-04',open='2026-11-04T14:30:00+00:00',close='2026-11-04T21:00:00+00:00'))
            value['calendar_bytes']=canonical(calendar)
            return value
        with patch.object(integration,'setup',calendar_with_later_session):
            self.daily=fixture(self.temp.name,extra_code_paths={SOURCE,STORE_SOURCE})
        self.now='2026-11-03T15:00:00+00:00';self.admitted={}
        first=self.daily['selection_result']
        self.arguments={first['decision_id']:self.daily['selection_arguments']}
        self.coordinator=self.make();self.book=self.coordinator.initialize()
        self.now='2026-11-03T15:00:03+00:00'
        self.coordinator.publish_target(first,expected_book_revision=self.book['revision'],previous_target_id=None)
        args=execution(self.daily,lambda:'2026-11-03T15:00:10+00:00');self.addCleanup(args['caps'].close)
        decision=produce_prospective_decision(**args)
        self.admitted[decision['decision_sha256']]=decision['decision_bytes']
        self.request=dict(kind='ACCEPT',operation_id='accept',expected_revision=self.book['revision'],
            decision_bytes=decision['decision_bytes'].decode())
        second_args=deepcopy(self.daily['selection_arguments']);second_args['now']='2026-11-03T15:00:02+00:00'
        self.second=select_prospective_target(clock=lambda:second_args['now'],**second_args)
        self.arguments[self.second['decision_id']]=second_args
        self.first=first;self.now='2026-11-03T15:00:11+00:00'

    def make(self, fault=None):
        return ProspectivePaperCoordinator(root=self.temp.name,authority=self.daily['authority'],
            admission_loader=lambda:dict(decisions=self.admitted,settlements={}),
            target_verifier=lambda result:verify_prospective_target(result,**self.arguments[result['decision_id']]),
            clock=lambda:datetime.fromisoformat(self.now),fault=fault,timeout_seconds=3)

    def test_accept_holds_shared_lock_through_commit_and_publication_loses_cas(self):
        entered=threading.Event();release=threading.Event();started=threading.Event();finished=threading.Event()
        errors=[];accepted=[]
        def fault(phase):
            if phase=='before_commit':
                entered.set();self.assertTrue(release.wait(5))
        def accept():
            try:accepted.append(self.make(fault).apply(self.request))
            except Exception as exc:errors.append(('accept',str(exc)))
        def publish():
            started.set()
            try:self.make().publish_target(self.second,expected_book_revision=self.book['revision'],previous_target_id=self.first['decision_id'])
            except Exception as exc:errors.append(('publish',str(exc)))
            finally:finished.set()
        one=threading.Thread(target=accept);one.start();self.assertTrue(entered.wait(5))
        two=threading.Thread(target=publish);two.start();started.wait(2)
        try:
            time.sleep(.1);self.assertFalse(finished.is_set())
        finally:release.set();one.join(5);two.join(5)
        self.assertFalse(one.is_alive() or two.is_alive())
        self.assertEqual(len(accepted),1)
        self.assertEqual(errors,[('publish','PAPER_TARGET_ACCOUNT_CAS')])
        self.assertEqual(self.make().current_target_id(),self.first['decision_id'])
        self.assertEqual(self.make().apply(self.request),accepted[0])

    def test_new_target_published_first_rejects_old_decision(self):
        self.make().publish_target(self.second,expected_book_revision=self.book['revision'],previous_target_id=self.first['decision_id'])
        self.assertEqual(self.make().current_target_id(),self.second['decision_id'])
        with self.assertRaisesRegex(ValueError,'CURRENT_TARGET_CHANGED'):self.make().apply(self.request)
        self.assertEqual(self.make().read(),self.book)
        self.assertEqual(self.make().publish_target(self.second,expected_book_revision='old',previous_target_id=None),self.second)

    def test_lost_target_tail_and_expired_publication_are_rejected(self):
        self.now='2026-11-03T15:03:10+00:00'
        with self.assertRaisesRegex(ValueError,'PUBLICATION_EXPIRED'):
            self.make().publish_target(self.second,expected_book_revision=self.book['revision'],previous_target_id=self.first['decision_id'])
        self.assertEqual(self.make().current_target_id(),self.first['decision_id'])
        connection=sqlite3.connect(self.coordinator.path)
        try:
            connection.execute('DELETE FROM paper_targets');connection.commit()
        finally:connection.close()
        with self.assertRaisesRegex(ValueError,'BUDGET'):self.make().current_target_id()

    def test_later_calendar_session_cannot_extend_registered_study(self):
        self.now='2026-11-04T15:00:11+00:00'
        with self.assertRaisesRegex(ValueError,'OUTSIDE_REGISTERED_STUDY'):
            self.make().publish_target(self.second,expected_book_revision=self.book['revision'],previous_target_id=self.first['decision_id'])
        self.assertEqual(self.make().current_target_id(),self.first['decision_id'])
        # An already published identical operation is a historical read.
        self.assertEqual(self.make().publish_target(self.first,expected_book_revision='old',previous_target_id=None),self.first)


if __name__=='__main__':unittest.main()
