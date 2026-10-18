import unittest
from backtest.return_priority_mature_rule_selection import select_mature_rule


class MatureRuleSelectionTests(unittest.TestCase):
    def inputs(self):
        return dict(decision_date='2026-04-01', candidate_statuses={'A':'LEGAL_INDICATIVE_ONLY', 'CASH':'REFERENCE_ALL_CASH'},
                    completed_blocks=[{'end_date':f'2026-0{i}-01', 'net_returns':{'A':v,'CASH':'0'}}
                                      for i,v in enumerate(('0.1','-0.1','0.1'),1)])

    def test_future_payload_not_read_and_exact_growth(self):
        args=self.inputs()
        expected=select_mature_rule(**args)
        args['completed_blocks'].append({'end_date':'2026-05-01','net_returns':object()})
        self.assertEqual(select_mature_rule(**args),expected)
        self.assertEqual(expected['selected_rule'],'A')
        self.assertEqual(expected['ranking'][0]['gross_growth_product'],'1089/1000')

    def test_missing_or_decision_blocked_never_imputed(self):
        args=self.inputs();args['completed_blocks'][0]['net_returns'].pop('A')
        self.assertEqual(select_mature_rule(**args)['selected_rule'],'CASH')
        args=self.inputs();args['candidate_statuses']['A']='BLOCKED'
        self.assertEqual(select_mature_rule(**args)['selected_rule'],'CASH')

    def test_common_window_and_insufficient_history(self):
        args=self.inputs();args['decision_date']='2026-02-01'
        self.assertEqual(select_mature_rule(**args)['status'],'INSUFFICIENT_MATURE_HISTORY')
        args=self.inputs();args.update(minimum_blocks=2,maximum_blocks=2)
        result=select_mature_rule(**args)
        self.assertEqual(result['selected_rule'],'CASH')
        self.assertEqual(result['training_end_dates'],['2026-02-01','2026-03-01'])

    def test_duplicate_dates_and_invalid_wealth_rejected(self):
        args=self.inputs();args['completed_blocks'].append(args['completed_blocks'][0])
        with self.assertRaises(ValueError):select_mature_rule(**args)
        args=self.inputs();args['completed_blocks'][0]['net_returns']['A']='-1'
        with self.assertRaises(ValueError):select_mature_rule(**args)


if __name__=='__main__':unittest.main()
