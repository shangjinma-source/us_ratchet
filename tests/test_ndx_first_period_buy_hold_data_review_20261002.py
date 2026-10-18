import unittest
from copy import deepcopy
from fractions import Fraction
from unittest.mock import Mock
from scripts import ndx_first_period_cash_buy_hold_account_20261002 as m
from backtest.ndx_cash_flow_return_accounting_research import account_path
from test_ndx_first_period_cash_buy_hold_account_20261002 import fixture

class IndependentTests(unittest.TestCase):
    def test_selected_source_and_pointer_are_authoritative(self):
        docs,refs=fixture();docs['repair_results']['rows'][2]['selected']['source']='NEW_REPAIR_BATCH'
        with self.assertRaisesRegex(ValueError,'fee mismatch'):m.assemble(docs,refs,account_path)
        docs,refs=fixture();docs['repair_results']['rows'][0]['previous_result_reference']['json_pointer']='/rows/1'
        blocked=Mock()
        with self.assertRaisesRegex(ValueError,'lineage'):m.assemble(docs,refs,blocked)
        blocked.assert_not_called()
    def test_later_flow_or_holdings_cannot_be_promoted(self):
        for field,value in (('cash_injection_usd','1000'),('buy_shares',{'A':1}),('holdings_after',{'A':999})):
            docs,refs=fixture()
            def corrupt(**kwargs):
                out=account_path(**kwargs);out['rows'][1][field]=value;return out
            with self.subTest(field=field),self.assertRaises(ValueError):m.assemble(docs,refs,corrupt)
    def test_close_is_not_replaced_by_open_and_evidence_retained(self):
        docs,refs=fixture();before=deepcopy(docs)
        docs['RETURN_price']['matrices']['close']['2023-09-01']['A']='11'
        result=m.assemble(docs,refs,account_path);row=result['rows'][0]
        self.assertEqual(m.from_ratio(row['account']['chained_twr']),Fraction(96,26000))
        self.assertEqual(row['quote_evidence'][-1]['quotes']['close']['A']['decimal_literal'],'11')
        self.assertEqual(row['quote_evidence'][-1]['quotes']['open']['A']['decimal_literal'],'10')
        self.assertEqual(result['price_evidence_metadata']['RETURN']['channels'],before['RETURN_price']['channels'])
        self.assertFalse(row['total_return_claimed']);self.assertEqual(row['input_row']['gaps'],['synthetic retained'])
    def test_cached_kernel_rejected(self):
        with self.assertRaisesRegex(ValueError,'cached'):m.load_account_path({})

if __name__=='__main__':unittest.main()
