from datetime import datetime,timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from backtest.current_strategy_paper_monthly_publish_v2 import publish_monthly_target,SOURCE
from backtest.current_strategy_paper_bootstrap_v2 import initialize_registered_paper
from backtest.current_strategy_prospective_paper_admission_store_v2 import ProspectivePaperAdmissionStore
from backtest.current_strategy_prospective_paper_admission_reader_v2 import registered_selection
from backtest.current_strategy_prospective_paper_coordinator_v2 import ProspectivePaperCoordinator
from data.strategy_prospective_paper_selection_v2 import select_prospective_target,verify_prospective_target
from data.strategy_paper_execution_preview_v1 import _local_import_closure
from prospective_paper_v2_fixture import fixture


class MonthlyPublishTests(unittest.TestCase):
    def test_archived_selection_recovers_without_second_source_or_search(self):
        with TemporaryDirectory() as folder:
            daily=fixture(folder,extra_code_paths=_local_import_closure({SOURCE,
                'backtest/current_strategy_paper_bootstrap_v2.py'}))
            now=['2026-11-03T15:00:00+00:00'];clock=lambda:datetime.fromisoformat(now[0])
            initialize_registered_paper(root=folder,authority=daily['authority'],clock=clock)
            store=ProspectivePaperAdmissionStore(root=Path(folder),authority=daily['authority'],clock=clock)
            def verify(result):
                recovered=registered_selection(store,result['decision_id'])
                return verify_prospective_target(result,**recovered['selection_arguments'])
            coordinator=ProspectivePaperCoordinator(root=folder,authority=daily['authority'],
                admission_loader=store.load,target_verifier=verify,clock=clock)
            calls=[]
            def sources(book,at):
                calls.append(at)
                return {k:v for k,v in daily['selection_arguments'].items()
                        if k not in ('book','authority','admitted_decisions','admitted_settlements','now')}
            now[0]='2026-11-03T15:00:01+00:00'
            def fail(phase):raise RuntimeError('interrupted before publish')
            args=dict(coordinator=coordinator,admission_store=store,source_loader=sources,clock=clock)
            with self.assertRaisesRegex(RuntimeError,'interrupted'):
                publish_monthly_target(**args,fault=fail)
            self.assertIsNone(coordinator.current_target_id())
            now[0]='2026-11-03T15:00:02+00:00'
            result=publish_monthly_target(**args)
            self.assertEqual(result['status'],'MONTHLY_TARGET_PUBLISHED')
            self.assertEqual(publish_monthly_target(**args)['status'],'MONTHLY_TARGET_ALREADY_PUBLISHED')
            self.assertEqual(len(calls),1)
            self.assertEqual(coordinator.read()['orders'],{})

    def test_realistic_advancing_clock_allows_processing_delay_but_not_stale_snapshot(self):
        with TemporaryDirectory() as folder:
            daily=fixture(folder)
            start=datetime.fromisoformat(daily['selection_arguments']['now'])
            ticks=[0]
            def clock():
                ticks[0]+=1
                return start+timedelta(microseconds=ticks[0])
            result=select_prospective_target(clock=clock,**daily['selection_arguments'])
            self.assertEqual(verify_prospective_target(result,**daily['selection_arguments'])['status'],'VERIFIED_SELECTION_ONLY')
            for seconds in (-1,121):
                with self.assertRaisesRegex(ValueError,'FRESH_CLOCK'):
                    select_prospective_target(clock=lambda:start+timedelta(seconds=seconds),**daily['selection_arguments'])


if __name__=='__main__':unittest.main()
