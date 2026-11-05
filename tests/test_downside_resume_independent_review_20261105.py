import unittest
from copy import deepcopy
import test_downside_independent_account_review_20261105 as fixtures
from scripts.research import review_downside_account_20261105_v2 as review


class ResumeIndependentReview(unittest.TestCase):
    def test_parent_and_new_month_pins_do_not_mix(self):
        selected,side,returns,qqq=fixtures.saved_tie_fixture()
        old=fixtures.fixture.RESEARCH;new={'new.py':'c'*64}
        day=selected['raw_selection']['decision_date']
        owner=review.pin_owner(day,old,new,{day})
        review.base.review_selection(selected,side,returns,qqq,owner)
        self.assertEqual(review.pin_owner('2099-01-31',old,new,{day}),new)
        with self.assertRaisesRegex(ValueError,'DYNAMIC_BINDING'):
            review.base.review_selection(selected,side,returns,qqq,new)

    def test_meta_complete_pair_wrong_amount_and_duplicate(self):
        a=review.base.read(review.ROOT/review.META_PATH)
        d=review.base.read(review.ROOT/'tmp/old_continuous_baseline_20261026_v9/execution_inputs.json')
        self.assertEqual(len(review.validate_meta_pairs(a,d['dividend_events'],d['provider_event_inventory'])),10)
        missing=deepcopy(a);missing['dividend_events'].pop()
        with self.assertRaisesRegex(ValueError,'TEN_COMPLETE'):
            review.validate_meta_pairs(missing,[],d['provider_event_inventory'])
        wrong=deepcopy(a);wrong['dividend_events'][0]['amount_per_share']='1'
        with self.assertRaisesRegex(ValueError,'NOMINAL_AMOUNT'):
            review.validate_meta_pairs(wrong,[],d['provider_event_inventory'])
        with self.assertRaisesRegex(ValueError,'ALREADY_PRESENT'):
            review.validate_meta_pairs(a,[a['dividend_events'][0]],d['provider_event_inventory'])


if __name__=='__main__':unittest.main()
