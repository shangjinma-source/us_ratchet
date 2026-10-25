from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from backtest.current_strategy_prospective_paper_admission_store_v2 import ProspectivePaperAdmissionStore, SOURCE
from data.strategy_paper_execution_preview_v1 import _local_import_closure
from data.strategy_prospective_paper_daily_capture_v2 import capture_prospective_daily
import test_strategy_prospective_paper_daily_capture_v2 as fixture


class DailySourceRegistryTests(unittest.TestCase):
    def test_register_reopen_select_parent_without_trade_admission(self):
        with TemporaryDirectory() as folder:
            args,_=fixture.arguments(folder,extra_code_paths=_local_import_closure({SOURCE}))
            captured=capture_prospective_daily(**args)
            store=ProspectivePaperAdmissionStore(root=folder,authority=args['authority'],clock=args['clock'])
            store.initialize()
            request=dict(daily_arguments=captured['daily_arguments'],directory=captured['directory'],
                trusted_complete_sha256=captured['archive_complete_sha256'])
            first=store.register_daily_source('first-source',**request)
            self.assertEqual(first['status'],'DAILY_SOURCE_REGISTERED_NOT_ORDER')
            self.assertEqual(store.register_daily_source('first-source',**request),first)
            reopened=ProspectivePaperAdmissionStore(root=folder,authority=args['authority'],clock=args['clock'])
            self.assertEqual(reopened.load(),dict(decisions={},settlements={}))
            self.assertIsNone(reopened.latest_daily_parent('B',before_session='2026-11-03'))
            parent=reopened.latest_daily_parent('B',before_session='2026-11-04')
            self.assertEqual(parent['session'],'2026-11-03')
            receipt=json.loads(parent['receipt_bytes'])
            self.assertEqual(sha256(parent['receipt_bytes']).hexdigest(),parent['trusted_parent_sha256'])
            self.assertEqual(set(receipt['source_sha256']),set(parent['files']))
            self.assertIsNone(reopened.latest_daily_parent('absent',before_session='2026-11-04'))
            # The journal's blob copy is authoritative, not a discovered file.
            blob=store.directory/sha256(b'first-source').hexdigest()/'blobs'/parent['trusted_parent_sha256']
            blob.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'BLOB_CHANGED'):
                reopened.latest_daily_parent('B',before_session='2026-11-04')


if __name__=='__main__':unittest.main()
