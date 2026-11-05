import unittest
from scripts.research.qqq_paid_reinvestment_20261106 import run_book
class ReinvestmentTests(unittest.TestCase):
 def run_case(self,amount,pay):
  days=['2024-01-01','2024-01-02','2024-01-03','2024-01-04','2024-01-05'];panel={d:dict(open='10',close='10') for d in days}
  return run_book(days,panel,[dict(ex_date='2024-01-03',payment_date=pay,amount=str(amount))],initial=101)
 def test_pay_close_not_open(self):
  b=self.run_case(2,'2024-01-03');self.assertEqual([r['date'] for r in b['order_log']],['2024-01-02','2024-01-04']);self.assertEqual(b['order_log'][1]['quantity'],2)
 def test_insufficient_cash_remains_unspent(self):
  b=self.run_case('0.1','2024-01-03');self.assertEqual(len(b['order_log']),1);self.assertEqual(b['daily_ledger'][-1]['shares'],10)
 def test_unpaid_not_buying_power(self):
  b=self.run_case(2,'2024-01-10');self.assertEqual(len(b['order_log']),1);self.assertEqual(b['daily_ledger'][-1]['dividend_receivable'],'20')
 def test_ex_date_new_shares_not_entitled(self):
  days=['2024-01-01','2024-01-02'];b=run_book(days,{days[1]:dict(open='10',close='10')},[dict(ex_date=days[1],payment_date=days[1],amount='20')],initial=101);self.assertEqual(b['claims'],[])
if __name__=='__main__':unittest.main()
