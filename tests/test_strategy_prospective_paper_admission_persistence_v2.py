from datetime import datetime
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import multiprocessing
from unittest.mock import patch
from backtest.current_strategy_prospective_paper_admission_store_v2 import ProspectivePaperAdmissionStore, SOURCE as ADMISSION_PIN
from data.strategy_paper_execution_preview_v1 import _local_import_closure

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


def reopen_worker(folder, daily, now, queue):
    try:
        archive=ProspectivePaperAdmissionStore(root=folder,authority=daily['authority'],clock=lambda:now)
        service=ProspectivePaperCoordinator(root=folder,authority=daily['authority'],admission_loader=archive.load,
            target_verifier=lambda target:verify_prospective_target(target,**daily['selection_arguments']),
            clock=lambda:datetime.fromisoformat(now))
        book=service.read()
        queue.put(dict(revision=book['revision'],orders=len(book['orders'])))
    except Exception as error:
        queue.put(dict(error=str(error)))


class PaperAdmissionPersistenceTests(unittest.TestCase):
    def test_reopen_same_target_caps_and_acceptance_without_duplicate_order(self):
        with TemporaryDirectory() as folder:
            daily=next_day(folder, extra_code_paths=CAP_PINS|{SOURCE,STORE_PIN}|_local_import_closure({ADMISSION_PIN}))
            authority=daily['authority']; admitted={}
            now=['2026-11-03T15:00:00+00:00']
            def archive():
                return ProspectivePaperAdmissionStore(root=folder,authority=authority,clock=lambda:now[0])
            archive().initialize()
            def coordinator(fault=None):
                return ProspectivePaperCoordinator(root=folder,authority=authority,
                    admission_loader=lambda:archive().load(),
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
            store=MonthlyPeakExitStore(archive().directory.parent/'risk.sqlite3')
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
            import json
            directory=Path(folder)/'synthetic-source-archive'
            directory.mkdir();(directory/'files').mkdir()
            receipt=json.loads(daily['receipt_bytes'])
            for name,raw in daily['files'].items():
                (directory/'files'/(sha256(raw).hexdigest()+'.bin')).write_bytes(raw)
            (directory/'receipt.json').write_bytes(daily['receipt_bytes'])
            complete=canonical(dict(schema='PROSPECTIVE_PAPER_DAILY_ARCHIVE_COMPLETE_V1',status='DAILY_SIGNAL_READY',
                receipt_sha256=daily['trusted_receipt_sha256'],source_sha256=receipt['source_sha256'],completed_at=now[0],
                account_id=book['account_id'],account_revision=book['revision'],target_id=signal['target_id'],descriptor_sha256=book['descriptor_sha256']))
            (directory/'complete.json').write_bytes(complete)
            anchor=dict(directory=str(directory),trusted_complete_sha256=sha256(complete).hexdigest())
            arguments=dict(daily_arguments=daily,execution_admission_bytes=admission,
                trusted_execution_admission_sha256=sha256(admission).hexdigest(),market_capture=market,unit_review=units,
                caps=caps,risk_store=store,cap_release_path='policy/cap.json')
            result=archive().produce_and_archive_decision('durable-decision',arguments,daily_archive=anchor)
            with patch('backtest.current_strategy_prospective_paper_admission_store_v2.produce_prospective_decision',
                       side_effect=AssertionError('must not rerun on reopen or retry')):
                self.assertIn(result['decision_sha256'],archive().load()['decisions'])
                self.assertEqual(archive().produce_and_archive_decision('durable-decision',arguments,daily_archive=anchor),result)
            admitted=archive().load()['decisions']
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
            context=multiprocessing.get_context('spawn')
            queue=context.Queue()
            process=context.Process(target=reopen_worker,args=(folder,daily,now[0],queue))
            process.start();process.join(30)
            if process.is_alive():
                process.terminate();process.join();self.fail('fresh process reopen timed out')
            self.assertEqual(process.exitcode,0)
            self.assertEqual(queue.get(timeout=5),dict(revision=accepted['revision'],orders=1))
            queue.close();queue.join_thread()
            caps.close()
            reopened=ProspectivePersistentCaps(root=folder,book=accepted,authority=authority,
                admitted_decisions=admitted,clock=lambda:now[0])
            self.addCleanup(reopened.close)
            self.assertEqual(reopened.namespace_id,caps.namespace_id)
            self.assertEqual(MonthlyPeakExitStore(store.path).read(signal['projection']['risk_namespace']),
                             saved_risk)
            import sqlite3
            with sqlite3.connect(store.path) as connection:
                connection.execute('DELETE FROM risk_state')
            connection.close()
            with self.assertRaisesRegex(ValueError,'PAPER_RISK_STATE_RECOVERY_REQUIRED'):
                archive().produce_and_archive_decision('must-not-reset-risk',arguments,daily_archive=anchor)
            self.assertFalse((archive().directory/sha256(b'must-not-reset-risk').hexdigest()).exists())
            # Missing server admission cannot be replaced by stored order bytes.
            blob=next((archive().directory/sha256(b'durable-decision').hexdigest()/'blobs').iterdir())
            blob.write_bytes(blob.read_bytes()+b'changed')
            with self.assertRaisesRegex(ValueError,'BLOB_CHANGED'):
                coordinator().read()


if __name__=='__main__':unittest.main()
