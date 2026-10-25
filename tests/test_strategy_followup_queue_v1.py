from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from data.strategy_daily_advice_journal_v1 import encoded
from data.strategy_followup_queue_v1 import IDENTITY_FIELDS,store_plans


class QueueTests(TestCase):
    def row(self):
        row={key:'value' for key in IDENTITY_FIELDS}
        row.update(side='BUY',order_index=0,horizon_sessions=1)
        row.update(observation_id=sha256(encoded(row)).hexdigest(),final_return_sha256='return',
            ticker='TEST',reference_limit='100',reference_quantity=2,reference_session='2026-10-20',
            observation_session='2026-10-21',observation_close='2026-10-21T20:00:00+00:00',capture_admitted=False)
        return row

    def test_restart_does_not_duplicate_or_save_stale_status(self):
        with TemporaryDirectory() as d:
            row=self.row();row['status']='WAIT_CLOSE'
            self.assertEqual(store_plans(d,[row])['created'],1)
            row['status']='DUE'
            self.assertEqual(store_plans(d,[row])['existing'],1)
            self.assertEqual(len(list(Path(d).glob('*.json'))),1)
            self.assertNotIn(b'WAIT_CLOSE',next(Path(d).glob('*.json')).read_bytes())

    def test_date_conflict_and_changed_identity_rejected(self):
        with TemporaryDirectory() as d:
            row=self.row();store_plans(d,[row]);changed=deepcopy(row)
            changed['observation_session']='2026-10-22'
            with self.assertRaisesRegex(ValueError,'QUEUE_PLAN_CONFLICT'):store_plans(d,[changed])
            changed=deepcopy(row);changed['side']='SELL'
            with self.assertRaisesRegex(ValueError,'QUEUE_IDENTITY_CHANGED'):store_plans(d,[changed])

    def test_unknown_calendar_and_admission_not_persisted(self):
        with TemporaryDirectory() as d:
            row=self.row();row['observation_session']=None
            self.assertEqual(store_plans(d,[row])['unresolved_calendar'],1)
            self.assertFalse(list(Path(d).iterdir()))
            row['capture_admitted']=True
            with self.assertRaisesRegex(ValueError,'QUEUE_DOES_NOT_ACCEPT_ADMISSION'):store_plans(d,[row])
