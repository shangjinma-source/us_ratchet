from datetime import datetime
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from core.strategy_account_ledger import canonical
from data.monthly_peak_exit_store import MonthlyPeakExitStore
from data.strategy_paper_application_descriptor_v2 import SCOPE
from data.strategy_prospective_paper_cap_daily_v2 import project_paper_cap_daily
from data.strategy_prospective_paper_cap_store_v2 import ProspectivePersistentCaps, CODE_PATHS as CAP_PINS
from data.strategy_prospective_paper_selection_v2 import verify_prospective_target
from data.strategy_prospective_paper_decision_v2 import produce_prospective_decision
from backtest.current_strategy_prospective_paper_coordinator_v2 import ProspectivePaperCoordinator, SOURCE
from backtest.current_strategy_prospective_paper_store_v2 import SOURCE as STORE_PIN
from test_strategy_prospective_paper_decision_v2 import next_day
from test_strategy_paper_execution_preview_v1 import capture


class PaperPersistenceTests(unittest.TestCase):
    def test_reopen_same_target_caps_and_acceptance_without_duplicate_order(self):
        with TemporaryDirectory() as folder:
            daily=next_day(folder, extra_code_paths=CAP_PINS|{SOURCE,STORE_PIN})
            authority=daily['authority']; admitted={}
            now=['2026-11-03T15:00:00+00:00']
            def coordinator(fault=None):
                return ProspectivePaperCoordinator(root=folder,authority=authority,
                    admission_loader=lambda:dict(decisions=admitted,settlements={}),
                    target_verifier=lambda target:verify_prospective_target(target,**daily['selection_arguments']),
                    clock=lambda:datetime.fromisoformat(now[0]),fault=fault)
            service=coordinator()
            self.assertEqual(service.initialize(),daily['book'])
            now[0]='2026-11-03T15:00:02+00:00'
            service.publish_target(daily['selection_result'],expected_book_revision=daily['book']['revision'],previous_target_id=None)
            now[0]=daily['now']
            book=coordinator().read()
            self.assertEqual(book,daily['book'])
            self.assertEqual(coordinator().current_target_id(),daily['selection_result']['decision_id'])
            store=MonthlyPeakExitStore(Path(folder)/'risk.sqlite')
            signal=project_paper_cap_daily(daily_arguments=daily,risk_store=store,cap_release_path='policy/cap.json')
            saved_risk=store.read(signal['projection']['risk_namespace'])
            caps=ProspectivePersistentCaps(root=folder,book=book,authority=authority,admitted_decisions=admitted,
                                          clock=lambda:now[0],initialize=True)
            self.addCleanup(caps.close)
            market,units=capture(book,datetime.fromisoformat(now[0]))
            admission=canonical(dict(schema='PROSPECTIVE_PAPER_EXECUTION_ADMISSION_V1',scope=SCOPE,
                descriptor_sha256=book['descriptor_sha256'],account_id=book['account_id'],account_revision=book['revision'],
                target_id=signal['target_id'],daily_evidence_id=signal['signal']['evidence_id'],cap_namespace_id=caps.namespace_id,
                source_sha256=market['source_hashes'],unit_review_sha256=sha256(canonical(units)).hexdigest(),available_at=now[0]))
            result=produce_prospective_decision(daily_arguments=daily,execution_admission_bytes=admission,
                trusted_execution_admission_sha256=sha256(admission).hexdigest(),market_capture=market,unit_review=units,
                caps=caps,clock=lambda:now[0],risk_store=store,cap_release_path='policy/cap.json')
            admitted[result['decision_sha256']]=result['decision_bytes']
            request=dict(kind='ACCEPT',operation_id='durable-buy',expected_revision=book['revision'],decision_bytes=result['decision_bytes'].decode())
            now[0]='2026-11-04T15:00:11+00:00'
            def interruption(phase):
                if phase=='before_commit':raise RuntimeError('simulated interruption before commit')
            with self.assertRaisesRegex(RuntimeError,'simulated interruption'):
                coordinator(fault=interruption).apply(request)
            self.assertEqual(coordinator().read(),book)
            accepted=coordinator().apply(request)
            self.assertEqual(len(accepted['orders']),1)
            self.assertEqual(coordinator().read(),accepted)
            self.assertEqual(coordinator().apply(request),accepted)
            caps.close()
            reopened=ProspectivePersistentCaps(root=folder,book=accepted,authority=authority,
                admitted_decisions=admitted,clock=lambda:now[0])
            self.addCleanup(reopened.close)
            self.assertEqual(reopened.namespace_id,caps.namespace_id)
            self.assertEqual(MonthlyPeakExitStore(store.path).read(signal['projection']['risk_namespace']),
                             saved_risk)
            # Missing server admission cannot be replaced by stored order bytes.
            admitted.clear()
            with self.assertRaisesRegex(ValueError,'NOT_SERVER_ADMITTED'):
                coordinator().read()


if __name__=='__main__':unittest.main()
