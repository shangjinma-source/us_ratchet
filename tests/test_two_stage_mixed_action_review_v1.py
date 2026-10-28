import unittest
from backtest.two_stage_execution_independent_review_v1 import opening_orders
class MixedActionTests(unittest.TestCase):
 def test_unrelated_integer_identity_cash_coordinates(self):
  orders=[dict(id='sell',security_id='old',quantity=1,side='SELL'),dict(id='stage',security_id='arm',quantity=24,side='BUY')]
  action=dict(type='split_identity',date='2024-10-01',security_id='old',new_security_id='new',old_shares='1',new_shares='10')
  result=opening_orders(orders,[action],'2024-10-01',{'stage'})
  self.assertEqual((result[0]['security_id'],result[0]['quantity']),('new',10));self.assertEqual(result[1],orders[1]);self.assertEqual(orders[0]['quantity'],1)
  with self.assertRaisesRegex(ValueError,'STAGE_ACTIVE_ACTION_NOT_SUPPORTED'):opening_orders(orders,[action],'2024-10-01',{'sell'})
 def test_fractional_conversion_not_silently_rounded(self):
  with self.assertRaisesRegex(ValueError,'STAGE_FRACTIONAL_ACTION_NOT_SUPPORTED'):opening_orders([dict(id='s',security_id='old',quantity=1)],[dict(type='split',date='d',security_id='old',old_shares='3',new_shares='1')],'d',set())
if __name__=='__main__':unittest.main()
