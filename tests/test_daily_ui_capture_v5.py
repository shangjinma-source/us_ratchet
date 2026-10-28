"""Current UI adapter retains real V3 financial checks; synthetic fixtures only."""
import unittest
from copy import deepcopy
import test_review_daily_ui_capture_v3 as prior_fixtures
from scripts.review_daily_ui_capture_v5 import review, HEADERS, UNREVIEWED

class CurrentCaptureTests(unittest.TestCase):
    def capture(self):
        c=prior_fixtures.FrontierReviewTests().capture()
        c['table_headers']=list(HEADERS)
        for row in c['visible_rows']: row['dom_cells'].append(UNREVIEWED)
        self.sync(c)
        return c
    def sync(self,c):
        c['page_text']='\n'.join(['\t'.join(c['table_headers'])]+['\t'.join(r['dom_cells']) for r in c['visible_rows']])
    def test_pass_preserves_input_and_rejects_ai_acceptance_claim(self):
        c=self.capture(); before=deepcopy(c);r=review(c)
        self.assertEqual(r['status'],'INTRADAY_UI_CHECKS_PASS');self.assertFalse(r['ai_risk_plan_accepted']);self.assertEqual(c,before)
    def test_exact_headers_and_column_count(self):
        for kind in ('old','missing','ninth','text'):
            c=self.capture()
            if kind=='old': c['table_headers'][4]='今日动作';self.sync(c)
            elif kind=='missing': del c['table_headers']
            elif kind=='ninth': c['visible_rows'][0]['dom_cells'].append('extra');self.sync(c)
            else: c['page_text']='missing'
            with self.subTest(kind=kind), self.assertRaises(ValueError):review(c)
    def test_all_other_ai_states_fail_closed(self):
        for label in ('未判断','复核中，原策略仍生效','复核已过期，待重新复核','未采用 卖出 5 股 $100','等待新报价','KEEP',''):
            c=self.capture();c['visible_rows'][0]['dom_cells'][7]=label;self.sync(c)
            with self.subTest(label=label),self.assertRaisesRegex(ValueError,'OUTSIDE_ACCEPTANCE_SCOPE'):review(c)
    def test_seven_financial_columns_still_checked(self):
        for index in range(1,7):
            c=self.capture();c['visible_rows'][0]['dom_cells'][index]='WRONG';self.sync(c)
            with self.subTest(index=index),self.assertRaises(ValueError):review(c)
    def test_quote_cash_account_and_binding_guards(self):
        for kind in ('expiry','cash','account','proposal'):
            c=self.capture()
            if kind=='expiry':c['state']['daily']['reference_quotes']['S']['reference_valid_until']=c['observed_at']
            elif kind=='cash':
                c['state']['account']['available_cash']='0'
                c['account_before']=deepcopy(c['state']['account'])
                c['account_after']=deepcopy(c['state']['account'])
            elif kind=='account':c['account_after']=dict(c['account_after'],revision='bad')
            else:c['state']['daily']['proposal_id']='b'*64
            with self.subTest(kind=kind):
                if kind=='cash':
                    with self.assertRaisesRegex(ValueError,'^USES_UNFILLED_SALE_CASH$'):review(c)
                else:
                    with self.assertRaises(ValueError):review(c)
    def test_wait_is_not_pass(self):
        c=self.capture();c['state']['daily'].update(status='WAIT',new_orders=[]);c['visible_rows'][0]['orders']=[]
        self.assertEqual(review(c)['status'],'NOT_ACCEPTED_WAIT')

if __name__=='__main__':unittest.main()
