import unittest
from copy import deepcopy
from scripts.research import review_downside_account_20261105_v9 as review

class V9Review(unittest.TestCase):
    def test_gehc_one_nominal_pair(self):
        artifact=review.base.read(review.ROOT/review.ARTIFACT)
        original=review.base.read(review.ROOT/'tmp/old_continuous_baseline_20261026_v9/execution_inputs.json')
        self.assertEqual(len(review.validate_gehc_pairs(artifact,original['dividend_events'],original['provider_event_inventory'])),1)
        bad=deepcopy(artifact);bad['dividend_events'][0]['payment_date']='2026-07-24'
        with self.assertRaisesRegex(ValueError,'FIXED_DATES'):review.validate_gehc_pairs(bad,[],original['provider_event_inventory'])
        bad=deepcopy(artifact);bad['review_rows'][0]['amount_per_share']='.35'
        with self.assertRaisesRegex(ValueError,'NOMINAL_AMOUNT'):review.validate_gehc_pairs(bad,[],original['provider_event_inventory'])
        with self.assertRaisesRegex(ValueError,'DUPLICATE'):review.validate_gehc_pairs(artifact,artifact['dividend_events'],original['provider_event_inventory'])

    def test_gehc_unpaid(self):
        event_id='gehc-gross:'+review.SID+':2026-07-24'
        book=dict(daily_ledger=[dict(date='2026-07-23',shares={review.SID:2}),dict(date='2026-07-30',dividend_receivable='.07')],dividend_ledger=dict(events={event_id:dict(opening_quantity=2,gross='.07',net='.07',event=dict(payment_date='2026-08-14'))},payments={},receivable='.07'))
        self.assertEqual(review.check_gehc_unpaid(book)['cash_paid'],'0')
        bad=deepcopy(book);bad['dividend_ledger']['payments']['bad']=dict(event_id=event_id)
        with self.assertRaisesRegex(ValueError,'EARLY_CASH'):review.check_gehc_unpaid(bad)

    def test_all_31_already_selected(self):
        parent=dict(records={str(i):{} for i in range(31)});summary=dict(searches=dict(new=31,reused=0,replayed=31))
        review.check_no_new_searches(parent,summary,parent['records'])
        with self.assertRaisesRegex(ValueError,'ALL_SELECTIONS'):review.check_no_new_searches(parent,summary,list(parent['records'])[:-1])
        summary['searches']['new']=32
        with self.assertRaisesRegex(ValueError,'NO_NEW_SEARCHES'):review.check_no_new_searches(parent,summary,parent['records'])

if __name__=='__main__':unittest.main()
