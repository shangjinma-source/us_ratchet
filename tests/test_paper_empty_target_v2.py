from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
import sqlite3
import unittest

from prospective_paper_v2_fixture import fixture
from data.strategy_paper_execution_preview_v1 import _local_import_closure
from data.strategy_prospective_paper_selection_v2 import verify_prospective_target,verify_empty_paper_target
from data.strategy_prospective_paper_daily_context_v2 import CapturedPaperDailyContext
from backtest.current_strategy_prospective_paper_run_once_v2 import ProspectivePaperRunOnce
from backtest.current_strategy_prospective_paper_admission_store_v2 import ProspectivePaperAdmissionStore
from backtest.current_strategy_prospective_paper_coordinator_v2 import ProspectivePaperCoordinator


class EmptyTargetTests(unittest.TestCase):
    def test_actual_empty_selection_holds_cash_without_quote_capture(self):
        with TemporaryDirectory() as folder:
            daily=fixture(folder,monthly_price='30000',extra_code_paths=_local_import_closure({
                'backtest/current_strategy_prospective_paper_run_once_v2.py',
                'data/strategy_prospective_paper_daily_context_v2.py',
                'backtest/current_strategy_prospective_paper_coordinator_v2.py'}))
            self.assertEqual(daily['selection_result']['payload']['target_quantities'],{})
            now=['2026-11-03T15:00:00+00:00'];clock=lambda:datetime.fromisoformat(now[0])
            store=ProspectivePaperAdmissionStore(root=folder,authority=daily['authority'],clock=clock)
            store.initialize();sqlite3.connect(store.directory.parent/'risk.sqlite3').close()
            coordinator=ProspectivePaperCoordinator(root=folder,authority=daily['authority'],admission_loader=store.load,
                target_verifier=lambda result:verify_prospective_target(result,**daily['selection_arguments']),clock=clock)
            coordinator.initialize();now[0]='2026-11-03T15:00:03+00:00'
            coordinator.publish_target(daily['selection_result'],expected_book_revision=daily['book']['revision'],previous_target_id=None)
            def forbidden(*args,**kwargs):raise AssertionError('empty cash account must not fetch quotes')
            context=CapturedPaperDailyContext(root=folder,authority=daily['authority'],admission_store=store,
                selection_loader=lambda target:dict(selection_result=daily['selection_result'],selection_arguments=daily['selection_arguments']),
                request_templates={},release_path='policy/daily.json',clock=clock,fetch_daily=forbidden,fetch_official=forbidden)
            runner=ProspectivePaperRunOnce(root=folder,authority=daily['authority'],coordinator=coordinator,
                admission_store=store,daily_context=context,identity_resolver=None,securities={},training_context={},
                cap_release_path='unused-empty-target',clock=clock,market_fetch=forbidden)
            before=coordinator.read()
            self.assertEqual(runner.run_once()['status'],'HOLD_EMPTY_TARGET')
            self.assertEqual(runner.run_once()['status'],'HOLD_EMPTY_TARGET')
            self.assertEqual(coordinator.read(),before)
            self.assertFalse((store.directory.parent/'daily-context').exists())

    def test_zero_cap_target_does_not_wait_for_configuration_close(self):
        from hashlib import sha256
        import json
        from core.strategy_account_ledger import canonical
        from data.monthly_peak_exit_store import MonthlyPeakExitStore
        from data.strategy_prospective_paper_cap_daily_v2 import project_paper_cap_daily
        release=canonical(dict(schema='PAPER_CAP_EXIT_DAILY_RELEASE_V2',policy_id='MONTHLY_CAP50_EXIT20',
            approved=True,scope='PAPER_DAILY_SIGNAL_RULE_ONLY',approved_at='2026-11-03T14:58:00+00:00'))
        # The second case has a real selected share but whole-share cap floors it to zero.
        for price in ('30000','20000'):
            with self.subTest(price=price), TemporaryDirectory() as folder:
                daily=fixture(folder,monthly_price=price,extra_sources={'policy/cap.json':release})
                inputs=json.loads(daily['files']['normalized.json'])
                if not daily['selection_result']['payload']['target_quantities']:
                    inputs['histories']={}
                    inputs['base_target']['price_units']={}
                daily['files']['normalized.json']=canonical(inputs)
                receipt=json.loads(daily['receipt_bytes'])
                receipt['source_sha256']={name:sha256(raw).hexdigest() for name,raw in daily['files'].items()}
                daily['receipt_bytes']=canonical(receipt)
                daily['trusted_receipt_sha256']=sha256(daily['receipt_bytes']).hexdigest()
                risk=MonthlyPeakExitStore(Path(folder)/'risk.sqlite3')
                result=project_paper_cap_daily(daily_arguments=daily,risk_store=risk,cap_release_path='policy/cap.json')
                self.assertEqual(result['status'],'DAILY_SIGNAL_READY')
                self.assertEqual(result['projection']['projection_kind'],'ZERO_MONTHLY_TARGET_EXIT')
                self.assertFalse(any(result['signal']['effective_target_quantities'].values()))
                self.assertIsNone(risk.read(result['projection']['risk_namespace']))
                daily['trusted_receipt_sha256']='0'*64
                with self.assertRaisesRegex(ValueError,'RECEIPT_HASH'):
                    project_paper_cap_daily(daily_arguments=daily,risk_store=risk,cap_release_path='policy/cap.json')

    def test_positive_target_cannot_claim_empty_hold(self):
        with TemporaryDirectory() as folder:
            daily=fixture(folder)
            with self.assertRaisesRegex(ValueError,'HAS_EXPOSURE'):
                verify_empty_paper_target(book=daily['book'],authority=daily['authority'],admitted_decisions={},
                    admitted_settlements={},selection_result=daily['selection_result'],selection_arguments=daily['selection_arguments'])


if __name__=='__main__':unittest.main()
