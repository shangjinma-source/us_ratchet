import unittest
from scripts.ndx_all_returned_split_status_research import forward,reverse_lcid

class EventBoundaries(unittest.TestCase):
    def test_forward_ex_date_not_payable(self):
        text='#55607 Date: November 26, 2024 Ex-Date: 12/16/2024 (PANW) has announced a 2 for 1 stock split. The Ex-distribution Date is December 16, 2024. The Payable Date is December 13, 2024. The Record Date is December 12, 2024. Effective Date: December 16, 2024 CUSIP:697435105'
        self.assertEqual(forward(text,ticker='PANW',session='2024-12-16',new_shares=2,cusip='697435105')['payable_date'],'2024-12-13')
        with self.assertRaises(ValueError):forward(text,ticker='PANW',session='2024-12-13',new_shares=2,cusip='697435105')

    def test_reverse_identity_not_option_symbol(self):
        text='(LCID) has announced a 1-for-10 reverse stock split. each LCID Common Share will be converted into the right to receive 0.1 (New) Lucid Group, Inc. Common Shares. effective before the market open on September 2, 2025. Effective Date:September 2, 2025 CUSIP: LCID (New): 549498202 Option Symbols:LCID changes to LCID1'
        result=reverse_lcid(text)
        self.assertEqual((result['ticker'],result['new_shares'],result['old_shares']),('LCID',1,10))
        self.assertTrue(result['identity_transition_requires_explicit_mapping'])
        for bad in [text.replace('549498202','549498103'),text.replace('0.1 (New)','10 (New)'),text.replace('Effective Date:September 2','Effective Date:September 3')]:
            with self.assertRaises(ValueError):reverse_lcid(bad)

    def test_crowdstrike_class_is_required(self):
        text='#59135 Date: June 09, 2026 Ex-Date: 07/02/2026 (CRWD) has announced a 4 for 1 stock split. The Ex-distribution Date is July 2, 2026. The Payable Date is July 1, 2026. The Record Date is June 25, 2026. Effective Date: July 2, 2026 CUSIP:22788C105 (CRWD) Class A Common Shares'
        self.assertEqual(forward(text,ticker='CRWD',session='2026-07-02',new_shares=4,cusip='22788C105')['security_class'],'CLASS_A_COMMON')
        with self.assertRaises(ValueError):forward(text.replace('Class A','Class B'),ticker='CRWD',session='2026-07-02',new_shares=4,cusip='22788C105')

if __name__=='__main__':unittest.main()
