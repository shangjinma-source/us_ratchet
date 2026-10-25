from copy import deepcopy
from datetime import datetime,timezone
from hashlib import sha256
from unittest import TestCase
from data.strategy_daily_advice_journal_v1 import encoded
from data.strategy_followup_queue_v1 import IDENTITY_FIELDS
from data.strategy_followup_capture_groups_v1 import group_due_observations


class GroupTests(TestCase):
    now=datetime(2026,10,22,21,tzinfo=timezone.utc)
    def row(self,event='a',side='BUY',close='2026-10-22T20:00:00+00:00'):
        row={k:'value' for k in IDENTITY_FIELDS}
        row.update(event_id=event,side=side,order_index=0,horizon_sessions=1)
        row['observation_id']=sha256(encoded(row)).hexdigest()
        row.update(observation_close=close,observation_session='2026-10-22',ticker='TEST',
            reference_session='2026-10-21',reference_limit='100' if side=='BUY' else '110',reference_quantity=2)
        return row
    def test_same_source_keeps_buy_and_sell_separate(self):
        rows=[self.row(),self.row('b','SELL')];before=deepcopy(rows)
        result=group_due_observations(rows,now=self.now)
        self.assertEqual(result['proposed_daily_requests'],1)
        self.assertEqual(result['due_observations'],2)
        self.assertEqual({r['reference_limit'] for r in result['groups'][0]['observations']},{'100','110'})
        self.assertFalse(result['capture_admitted']);self.assertEqual(rows,before)
    def test_future_close_ignores_stale_due_label(self):
        row=self.row(close='2026-10-23T20:00:00+00:00');row['status']='DUE'
        result=group_due_observations([row],now=self.now)
        self.assertEqual(result['due_observations'],0);self.assertEqual(result['waiting_observations'],1)
    def test_duplicate_and_ticker_conflict_rejected(self):
        row=self.row()
        with self.assertRaisesRegex(ValueError,'GROUP_OBSERVATION_IDENTITY'):
            group_due_observations([row,row],now=self.now)
        other=self.row('b');other['ticker']='WRONG'
        with self.assertRaisesRegex(ValueError,'GROUP_TICKER_CONFLICT'):
            group_due_observations([row,other],now=self.now)
