import unittest
from copy import deepcopy
from scripts.research import review_downside_account_20261105_v8 as review

class V8Review(unittest.TestCase):
    def test_final_gross_not_initial_or_net(self):
        a=review.base.read(review.ROOT/review.ARTIFACT)
        d=review.base.read(review.ROOT/'tmp/old_continuous_baseline_20261026_v9/execution_inputs.json')
        self.assertEqual(len(review.validate_asml_pairs(a,d['dividend_events'],d['provider_event_inventory'])),2)
        for amount in ['3.177','2.693183']:
            bad=deepcopy(a);bad['dividend_events'][0]['amount_per_share']=amount
            with self.assertRaisesRegex(ValueError,'GROSS_NOT_ESTIMATE_OR_NET'):review.validate_asml_pairs(bad,[],d['provider_event_inventory'])
        bad=deepcopy(a);bad['review_rows'][0]['final_announcement_date']='2026-04-27'
        with self.assertRaisesRegex(ValueError,'TIMING_AND_UNIT'):review.validate_asml_pairs(bad,[],d['provider_event_inventory'])

    def test_july_not_spendable_before_august(self):
        event_id='asml-final-gross:'+review.SID+':2026-07-28'
        book=dict(daily_ledger=[dict(date='2026-07-27',shares={review.SID:2}),dict(date='2026-07-30',dividend_receivable='4.275496')],dividend_ledger=dict(events={event_id:dict(opening_quantity=2,gross='4.275496',net='4.275496',event=dict(payment_date='2026-08-05'))},payments={},receivable='4.275496'))
        self.assertEqual(review.check_july_unpaid(book)['july_cash_paid'],'0')
        bad=deepcopy(book);bad['dividend_ledger']['payments']['bad']=dict(event_id=event_id)
        with self.assertRaisesRegex(ValueError,'EARLY_CASH'):review.check_july_unpaid(bad)

if __name__=='__main__':unittest.main()
