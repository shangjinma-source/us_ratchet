import copy
import unittest
from scripts.audit_monthly_selection_endpoint import compare_selection


class SelectionAuditTests(unittest.TestCase):
    def fixture(self):
        args=dict(prices={'A':'6','B':'2'},metadata={'A':{'ticker':'A'},'B':{'ticker':'B'}},
            decision_date='2024-01-31',scenario_dates=['2024-01-16','2024-01-31'],
            training_scenarios=[{'A':'2','B':'1'},{'A':'2','B':'2'}],fee_bps='0',minimum_cash_buffer='0')
        window=dict(decision_date='2024-01-31',active_date='2024-02-01',training_dates=['2024-01-01','2024-01-16','2024-01-31'],
            search_arguments=args,candidates=[dict(security_id='A',training_close=['1','2','4'],training_gross=['2','2'],decision_cost='6'),
                                             dict(security_id='B',training_close=['1','1','2'],training_gross=['1','2'],decision_cost='2')])
        selected=dict(quantities={'A':1},residual_cash='4',fees='0')
        selection=dict(decision_date='2024-01-31',investable_equity='10',target_quantities={'A':1},
            search_result=dict(decision_date='2024-01-31',scenario_dates=args['scenario_dates'],entered_cash='10',
                               fee_bps='0',minimum_cash_buffer='0',selected=selected))
        return window,selection

    def test_exact_integer_match_is_not_fractional_training_identity(self):
        window,selection=self.fixture();row=compare_selection(window,selection)
        self.assertTrue(row['same_full_cash_integer_target'])
        self.assertEqual(row['selected_scenario_wealth_product'],'64/25')
        self.assertEqual(row['endpoint_top_ties'][0]['growth'],'4')

    def test_multistock_difference_reports_no_performance_conclusion(self):
        window,selection=self.fixture();selection['target_quantities']={'A':1,'B':2}
        selection['search_result']['selected'].update(quantities=selection['target_quantities'],residual_cash='0')
        row=compare_selection(window,selection)
        self.assertFalse(row['same_single_stock_support'])
        self.assertEqual(row['conclusion'],'DIFFERENT_TARGET_NO_PERFORMANCE_CONCLUSION')

    def test_wrong_scenario_cash_and_future_dates_rejected(self):
        for mutation,reason in [
            (lambda w,s:w['candidates'][0]['training_close'].__setitem__(-1,'5'),'ENDPOINT'),
            (lambda w,s:s['search_result']['selected'].update(residual_cash='0'),'CASH'),
            (lambda w,s:w['training_dates'].__setitem__(-1,'2024-02-02'),'NONCAUSAL')]:
            window,selection=self.fixture();mutation(window,selection)
            with self.assertRaisesRegex(ValueError,reason):compare_selection(window,selection)


if __name__=='__main__':unittest.main()
