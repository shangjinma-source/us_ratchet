from copy import deepcopy
from pathlib import Path
import json
import tempfile
import unittest

from data.current_research_intraday_execution import IntradayExecutionService
from data.current_research_intraday_cap_store import PersistentIntradayCapStore
from data.current_research_intraday_journal import IntradayObservationJournal
from data.current_research_intraday_journal_reference import _PinnedJournal, read_journal_execution_reference
from data.current_research_intraday_review import review_intraday_session
from test_current_research_intraday_execution import NOW,payload,snapshot


class PinnedClosureTests(unittest.TestCase):
    def test_missing_failed_sequence_is_not_missing_cap_dependency(self):
        with tempfile.TemporaryDirectory() as directory:
            journal=IntradayObservationJournal(Path(directory)/'journal')
            service=IntradayExecutionService(snapshot_reader=snapshot,fetch=lambda _:payload(),clock=lambda:NOW,
                journal=journal,cap_store=PersistentIntradayCapStore(Path(directory)/'cap.sqlite3'))
            first=service.preview('a'*24)
            service.fetch=lambda _:(_ for _ in ()).throw(OSError('synthetic offline'))
            failed=service.preview('a'*24)
            service.fetch=lambda _:payload()
            latest=service.preview('a'*24)
            self.assertEqual(failed['status'],'UNAVAILABLE')
            self.assertEqual(latest['observation_sequence'],3)
            hashes={};files={}
            for response in (first,latest):
                receipt=response['observation_record'];name=receipt['event_path']
                hashes[name]=receipt['event_sha256'];files[name]=(journal.root/name).read_bytes()
                for capture in json.loads(files[name])['captures']:
                    files[capture['path']]=(journal.root/capture['path']).read_bytes()
            pinned=_PinnedJournal(files)
            full=review_intraday_session('', '2026-10-15', expected_event_hashes=hashes,journal=pinned)
            self.assertEqual(full['status'],'INCOMPLETE')
            self.assertIn('MISSING_SEQUENCE_RANGE:2..2',str(full))
            closure=review_intraday_session('', '2026-10-15', expected_event_hashes=hashes,journal=pinned,inventory_scope='PINNED_CAP_CLOSURE')
            self.assertEqual(closure['status'],'REVIEWED_LOCAL_OBSERVATIONS')
            self.assertIn('DOES_NOT_PROVE_FULL_SESSION_OR_LATEST',str(closure['coverage_notes']))
            binding=dict(account_id='synthetic',target_month='2026-10',research_id='a'*24,
                security_id='sndk',ticker='SNDK',session='2026-10-15')
            reference=read_journal_execution_reference(root=journal.root,binding=binding,
                current_reference=service.current_reference('a'*24),event_hashes=hashes,now=NOW)
            self.assertEqual(reference['buy_limit'],'35303/25')
            only_latest={latest['observation_record']['event_path']:latest['observation_record']['event_sha256']}
            with self.assertRaisesRegex(ValueError,'DEPENDENCY'):
                read_journal_execution_reference(root=journal.root,binding=binding,
                    current_reference=service.current_reference('a'*24),event_hashes=only_latest,now=NOW)
            with self.assertRaisesRegex(ValueError,'INVENTORY_MISMATCH'):
                review_intraday_session('', '2026-10-15', expected_event_hashes=only_latest,journal=pinned,inventory_scope='PINNED_CAP_CLOSURE')
            with self.assertRaisesRegex(ValueError,'RECEIPTS_REQUIRED'):
                review_intraday_session('', '2026-10-15',journal=pinned,inventory_scope='PINNED_CAP_CLOSURE')


if __name__=='__main__': unittest.main()
