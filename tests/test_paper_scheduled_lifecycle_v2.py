from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from copy import deepcopy
import unittest

from scripts.run_prospective_paper_v2 import run_scheduled,load_runner
from test_paper_runtime_initialization_v2 import configured


class ScheduledLifecycleTests(unittest.TestCase):
    def test_wait_initialize_and_repeat_without_duplicate_cash(self):
        with TemporaryDirectory() as folder:
            args=configured(folder)
            now=['2026-11-03T14:59:30+00:00']
            args['clock']=lambda:datetime.fromisoformat(now[0])
            self.assertEqual(run_scheduled(**args)['status'],'WAIT_REGISTERED_START')
            self.assertFalse(list(Path(folder).rglob('book.sqlite3')))
            now[0]='2026-11-03T15:00:10+00:00'
            # This test exercises actual configuration/registration/bootstrap/replay.
            # Capture and trading are verified separately and never call HTTP here.
            with patch('scripts.run_prospective_paper_v2.ProspectivePaperRunOnce.publish_monthly',
                    return_value={'status':'MONTHLY_TARGET_ALREADY_PUBLISHED'}) as publish, \
                 patch('scripts.run_prospective_paper_v2.ProspectivePaperRunOnce.run_once',
                    return_value={'status':'TEST_DAILY_DISPATCH'}) as daily:
                self.assertEqual(run_scheduled(**args)['status'],'TEST_DAILY_DISPATCH')
                first=load_runner(**args).coordinator.read()
                self.assertEqual(run_scheduled(**args)['status'],'TEST_DAILY_DISPATCH')
                self.assertEqual(load_runner(**args).coordinator.read(),first)
                self.assertEqual(first['cash'],'20000')
                self.assertEqual(publish.call_count,2)
                self.assertEqual(daily.call_count,2)

    def test_missed_first_window_never_backfills(self):
        with TemporaryDirectory() as folder:
            args=configured(folder);args['clock']=lambda:datetime.fromisoformat('2026-11-03T15:02:00+00:00')
            with self.assertRaisesRegex(ValueError,'MISSED_REGISTERED_START'):
                run_scheduled(**args)
            self.assertFalse(list(Path(folder).rglob('book.sqlite3')))

    def test_settlement_then_today_only_when_book_closed_and_window_remains(self):
        with TemporaryDirectory() as folder:
            args=configured(folder)
            now=['2026-11-03T15:00:10+00:00']
            args['clock']=lambda:datetime.fromisoformat(now[0])
            runner=load_runner(**args,initialize=True)
            closed=runner.coordinator.read()
            pending=deepcopy(closed);pending['orders']={'prior':{'closed':None}}
            # Exercise scheduling against a real registered authority/calendar.
            # Settlement and coordinator reads are seams: ledger correctness is
            # covered by the settlement integration tests, not claimed here.
            for remains_pending,late in ((False,False),(True,False),(False,True)):
                now[0]='2026-11-03T15:00:10+00:00'
                calls=[]
                def run():
                    calls.append('run')
                    if len(calls)==1:
                        if late:now[0]='2026-11-03T15:01:01+00:00'
                        return {'status':'TEST_SETTLED'}
                    return {'status':'TEST_TODAY'}
                with patch('scripts.run_prospective_paper_v2.load_runner',return_value=runner), \
                     patch.object(runner.coordinator,'read',side_effect=[pending,pending if remains_pending else closed]), \
                     patch.object(runner,'run_once',side_effect=run), \
                     patch.object(runner,'publish_monthly',return_value={'status':'MONTHLY_TARGET_ALREADY_PUBLISHED'}) as publish:
                    result=run_scheduled(**args)
                if remains_pending or late:
                    self.assertEqual(result['status'],'TEST_SETTLED')
                    self.assertEqual(len(calls),1);publish.assert_not_called()
                else:
                    self.assertEqual(result['status'],'TEST_TODAY')
                    self.assertEqual(result['settlement']['status'],'TEST_SETTLED')
                    self.assertEqual(len(calls),2);publish.assert_called_once()
            self.assertEqual(runner.coordinator.read(),closed)


if __name__=='__main__':unittest.main()
