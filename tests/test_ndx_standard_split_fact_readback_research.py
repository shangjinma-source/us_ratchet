import unittest
from scripts.ndx_standard_split_fact_readback_research import parse_occ

TEXT='''#51729 Date: January 05, 2023 Subject: PACCAR Inc. - 3 For 2 Stock Split
Option Symbol: PCAR New Option Symbol: PCAR1 Ex-Date: 02/08/2023
PACCAR Inc. (PCAR) has announced a 3 for 2 stock split. The Ex-distribution Date is February 8, 2023.
The Payable Date is February 7, 2023. The Record Date is January 17, 2023.
Contract Adjustment Effective Date: February 8, 2023 Option Symbol: PCAR changes to PCAR1
New Multiplier: 150 Contract Multiplier: 1 Strike Divisor: 1.50
New Deliverable Per Contract: 150 PACCAR Inc. (PCAR) Common Shares CUSIP: 693718108'''
EXPECTED=dict(ticker='PCAR',session='2023-02-08',new_shares=3,old_shares=2,cusip='693718108')


class EventTests(unittest.TestCase):
    def test_equity_ratio_is_not_contract_multiplier_or_option_symbol(self):
        result=parse_occ(TEXT,**EXPECTED)
        self.assertEqual((result['new_shares'],result['old_shares'],result['ticker']),(3,2,'PCAR'))
        self.assertNotEqual(result['payable_date'],result['first_adjusted_trading_date'])

    def test_wrong_cusip_rejected(self):
        with self.assertRaises(ValueError):parse_occ(TEXT.replace('693718108','023135106'),**EXPECTED)

    def test_conflicting_ex_date_header_rejected(self):
        with self.assertRaises(ValueError):parse_occ(TEXT.replace('Ex-Date: 02/08/2023','Ex-Date: 02/07/2023'),**EXPECTED)

    def test_duplicate_or_mismatched_stock_clause_rejected(self):
        with self.assertRaises(ValueError):parse_occ(TEXT.replace('has announced a 3 for 2','has announced a 2 for 1'),**EXPECTED)
        with self.assertRaises(ValueError):parse_occ(TEXT+' PACCAR Inc. (PCAR) has announced a 3 for 2 stock split.',**EXPECTED)


if __name__=='__main__':unittest.main()
