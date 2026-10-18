from copy import deepcopy
import unittest
from backtest.return_priority_monthly_execution_inputs import assemble_monthly_execution_inputs, BASIS

class AssemblyTests(unittest.TestCase):
    def setUp(self):
        self.p=dict(session_dates=['2024-01-31','2024-02-01'],source_hashes={'raw':'a'*64,'backtest/return_priority_fresh_cash_quantity_search.py':'b'*64},
            metadata={s:dict(ticker=s,issuer_id=s) for s in ['A','X','Y']},
            source_provenance={s:dict(whole_source='raw',price_basis=BASIS) for s in ['A','X','Y']},
            ohlc={s:{'2024-01-31':dict(close='10'),'2024-02-01':dict(close='5')} for s in ['A','X','Y']},
            windows=[dict(decision_date='2024-01-31',search_arguments=dict(decision_date='2024-01-31',prices={'A':'10'},metadata={'A':dict(ticker='A',issuer_id='A')},training_scenarios=[{'A':'1.1'}]))],
            split_events_reference_only=[dict(date='2024-02-01',security_id='X',new_shares=2,old_shares=1,source_references=['raw'])],
            identity_migrations=[dict(date='2024-02-01',old_sid='X',new_sid='Y',new_shares=2,old_shares=1,source_references=['raw'])],
            cash_stock_merger_events=[{'event_id':'mixed','effective_date':'2024-02-01','old_sid':'X','source_references':['raw']}],fractional_settlements={'mixed':{'known_asof':'2024-02-01'}})

    def test_full_domain_residual_quotes_exact_and_no_mutation(self):
        before=deepcopy(self.p);result=assemble_monthly_execution_inputs(self.p)
        self.assertEqual(self.p,before)
        row=result['monthly_inputs'][0]
        self.assertEqual(set(row['search_arguments']['prices']),{'A'})
        self.assertEqual({q['security_id'] for q in row['valuation_quotes']},{'A','X','Y'})
        self.assertEqual(row['search_arguments']['quote_as_of'],'2024-01-31')
        self.assertEqual(result['actions'][0]['type'],'split_identity');self.assertEqual(len(result['actions']),1)
        self.assertEqual(len(result['provider_actions']),2)
        self.assertEqual(result['provider_actions'][-1]['type'],'cash_stock_merger')
        self.assertEqual(result['actions'][0]['new_security_id'],'Y')
        self.assertEqual(result['cash_stock_merger_events'],self.p['cash_stock_merger_events'])
        self.assertEqual(result['fractional_settlements'],self.p['fractional_settlements'])

    def test_missing_residual_mark_is_explicit_not_zero(self):
        self.p['ohlc']['X']['2024-01-31']['close']=None
        r=assemble_monthly_execution_inputs(self.p)
        self.assertEqual(r['monthly_inputs'][0]['missing_historical_marks'],['X'])
        self.assertNotIn('2024-01-31',r['close_prices']['X'])
        self.assertEqual(set(r['monthly_inputs'][0]['search_arguments']['prices']),{'A'})

    def test_candidate_missing_and_subcent_mismatch_fail(self):
        self.p['ohlc']['A']['2024-01-31']['close']=None
        with self.assertRaisesRegex(ValueError,'MISSING_CANDIDATE'):assemble_monthly_execution_inputs(self.p)
        self.p['ohlc']['A']['2024-01-31']['close']='9.9999999'
        with self.assertRaisesRegex(ValueError,'PRICE_MISMATCH'):assemble_monthly_execution_inputs(self.p)

    def test_incomplete_domain_and_conflicting_split_fail(self):
        self.p['windows'][0]['search_arguments']['training_scenarios']=[{}]
        with self.assertRaisesRegex(ValueError,'INCOMPLETE_SEARCH_DOMAIN'):assemble_monthly_execution_inputs(self.p)
        self.setUp();self.p['identity_migrations'][0]['new_shares']=3
        with self.assertRaisesRegex(ValueError,'RATIO_CONFLICT'):assemble_monthly_execution_inputs(self.p)

if __name__=='__main__':unittest.main()
