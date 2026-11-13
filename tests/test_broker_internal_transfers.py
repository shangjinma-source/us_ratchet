import unittest
from datetime import datetime, timezone
from core.broker_internal_transfers import create_transfers, apply_transfer_event, project_transfers


class InternalTransferTests(unittest.TestCase):
    now = datetime(2026,11,15,tzinfo=timezone.utc)

    def sent(self):
        state = create_transfers('isolated-test')
        event = dict(event_id='send', transfer_id='t1', kind='SENT', source='HSBC',
            destination='USMART', principal='600', fee='5', occurred_at='2026-11-14T00:00:00+08:00')
        return apply_transfer_event(state,event,expected_revision=state['revision'],now=self.now),event

    def receive(self,state,amount,event_id='receipt',at='2026-11-15T00:00:00+08:00'):
        event=dict(event_id=event_id,transfer_id='t1',kind='RECEIVED',amount=amount,occurred_at=at)
        return apply_transfer_event(state,event,expected_revision=state['revision'],now=self.now)

    def test_cross_day_partial_receipts_conserve_principal(self):
        state,_=self.sent()
        for amount,pending,event_id in [('200','400','r1'),('400','0','r2')]:
            state=self.receive(state,amount,event_id)
            result=project_transfers(state)
            self.assertEqual(result['in_transit_usd'],pending)
            self.assertEqual(result['external_capital_flow_usd'],'0')
            self.assertEqual(result['confirmed_fees_usd'],'5')
            self.assertFalse(result['in_transit_is_buying_power'])
        self.assertEqual(result['transfers']['t1']['status'],'RECEIVED')

    def test_idempotent_retry_never_duplicates_assets(self):
        state,event=self.sent()
        self.assertEqual(apply_transfer_event(state,event,expected_revision='old',now=self.now),state)
        received=self.receive(state,'600')
        self.assertEqual(self.receive(received,'600'),received)

    def test_same_day_transfer_preserves_assets_except_explicit_fee(self):
        state,_=self.sent()
        # Starting 1000, source debit 605: settled 395 plus in-transit 600.
        self.assertEqual(395+int(project_transfers(state)['in_transit_usd']),995)
        state=self.receive(state,'600',at='2026-11-14T01:00:00+08:00')
        self.assertEqual(395+600+int(project_transfers(state)['in_transit_usd']),995)

    def test_overreceipt_and_backdated_receipt_rejected(self):
        state,_=self.sent()
        for amount,at in [('601','2026-11-15T00:00:00+08:00'),('1','2026-11-13T00:00:00+08:00')]:
            with self.assertRaises(ValueError):self.receive(state,amount,at=at)
        self.assertEqual(project_transfers(state)['in_transit_usd'],'600')

    def test_conflicting_retry_and_stale_revision_rejected(self):
        state,event=self.sent()
        with self.assertRaisesRegex(ValueError,'EVENT_ID_CONFLICT'):
            apply_transfer_event(state,dict(event,principal='700'),expected_revision=state['revision'],now=self.now)
        with self.assertRaisesRegex(ValueError,'STALE_REVISION'):
            apply_transfer_event(state,dict(event,event_id='another'),expected_revision='old',now=self.now)


if __name__=='__main__':unittest.main()
