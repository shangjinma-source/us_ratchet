from copy import deepcopy
import unittest

from data.current_research_limit_plan import build_current_research_limit_plan
from data.current_research_fill_ledger import initialize_paper_ledger, apply_paper_fill, apply_paper_order_event
from data.current_research_plan_review import review_research_plan


def state_fixture(sell=False, empty=False):
    plan = build_current_research_limit_plan(
        research_snapshot=dict(research_id='a'*24, as_of='2026-10-13', stocks=[dict(security_id='A', ticker='AAA')], source_hashes={'quote':'b'*64}),
        quotes=[dict(security_id='A',price='10',as_of='2026-10-13',price_kind='DECLARED_DECIMAL_REFERENCE',price_basis='CONDITIONAL',source_references=['quote'])],
        available_cash='100', shares={'A':3} if sell else {}, account_revision='initial',
        decision_date='2026-10-13',active_date='2026-10-14',calendar=['2026-10-13','2026-10-14'],
        strategy_version='fixed',target_quantities={} if sell or empty else {'A':3})
    return initialize_paper_ledger(plan,'paper-test')


def bar(low='9', high='11', day='2026-10-14'):
    return dict(security_id='A', session=day, open='10',high=high,low=low,close='10',source_references=['daily'])


class PlanReviewTests(unittest.TestCase):
    def review(self,state,bars,cutoff='2026-10-14'):
        return review_research_plan(state=state,observed_through=cutoff,market_bars=bars,source_hashes={'daily':'c'*64})

    def test_buy_sell_touch_exact_boundary_and_no_state_mutation(self):
        for sell in (False,True):
            state=state_fixture(sell); before=deepcopy(state)
            result=self.review(state,[bar(low='10',high='10')])
            self.assertEqual(result['orders'][0]['observed_touch'],'YES')
            self.assertFalse(result['orders'][0]['fill_inferred'])
            self.assertEqual(state,before)
            miss=bar(low='11',high='12') if not sell else bar(low='8',high='9')
            miss['open']=miss['close']='11' if not sell else '9'
            self.assertEqual(self.review(state,[miss])['orders'][0]['observed_touch'],'NO')

    def test_missing_other_day_and_uncompleted_day_unknown(self):
        state=state_fixture()
        self.assertEqual(self.review(state,[])['orders'][0]['observed_touch'],'UNKNOWN')
        self.assertEqual(self.review(state,[bar(day='2026-10-13')])['orders'][0]['observed_touch'],'UNKNOWN')
        self.assertEqual(self.review(state,[],cutoff='2026-10-13')['orders'][0]['reason'],'ORDER_SESSION_AFTER_OBSERVATION_CUTOFF')
        with self.assertRaises(ValueError):self.review(state,[bar()],cutoff='2026-10-13')

    def test_partial_then_cancelled_keeps_recorded_quantities_not_opportunity(self):
        state=state_fixture();order=state['plan']['orders'][0]
        state=apply_paper_fill(state,dict(event_id='f',mode='PAPER_MANUAL_FILL',plan_id=state['plan']['plan_id'],order_id=order['order_id'],qty=1,price='9',fees='0',session='2026-10-14',expected_revision=state['revision']))
        state=apply_paper_order_event(state,dict(event_id='c',mode='PAPER_MANUAL_FILL',event_type='CANCEL',plan_id=state['plan']['plan_id'],order_id=order['order_id'],expected_revision=state['revision']))
        r=self.review(state,[bar()])['orders'][0]
        self.assertEqual((r['filled_quantity'],r['unfilled_quantity'],r['order_status']),(1,2,'CANCEL'))
        self.assertEqual(r['observed_touch'],'YES')
        self.assertFalse(r['execution_opportunity_established'])

    def test_invalid_data_rejected_and_empty_orders_valid(self):
        cases=[[bar(),bar()],[bar(low='12')],[dict(bar(),close='0')],[dict(bar(),open=True)],[dict(bar(),close='nan')],[dict(bar(),source_references=['unbound'])]]
        for bars in cases:
            with self.subTest(bars=bars),self.assertRaises(ValueError):self.review(state_fixture(),bars)
        self.assertEqual(self.review(state_fixture(empty=True),[])['orders'],[])


if __name__=='__main__':unittest.main()
