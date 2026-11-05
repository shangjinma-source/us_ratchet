import unittest
from fractions import Fraction as F
from datetime import date
from scripts.research.summarize_momentum_account_20261105 import measure

class MeasureTests(unittest.TestCase):
 def test_year_returns_drawdown_and_two_sided_turnover(self):
  rows=[dict(date='2024-01-02',equity='20000',shares={'a':10}),dict(date='2024-12-31',equity='22000',shares={'a':10}),dict(date='2025-12-31',equity='19800',shares={})]
  orders=[dict(event='ASSUMED_NEXT_OPEN_FILLED',date='2024-01-02',quantity=10,price='1000',side='BUY'),dict(event='ASSUMED_NEXT_OPEN_FILLED',date='2025-12-31',quantity=10,price='900',side='SELL'),dict(event='REJECTED',date='2025-01-02',quantity=100,price='1')]
  result=measure(rows,'2023-12-29',orders)
  self.assertEqual(result['fills'],2);self.assertAlmostEqual(result['drawdown_pct'],10)
  self.assertAlmostEqual(result['annual']['2024']['return_pct'],10);self.assertAlmostEqual(result['annual']['2025']['return_pct'],-10)
  years=F((date(2025,12,31)-date(2023,12,29)).days,1)/F('365.25');average=F(61800,3)
  self.assertEqual(result['turnover']['gross_traded_notional_exact'],'19000')
  self.assertAlmostEqual(result['turnover']['annualized_gross_turnover'],float(F(19000)/average/years))
 def test_partial2026_exclusion_and_qqq_missing_not_guessed(self):
  rows=[dict(date='2025-12-31',equity='21000',shares=1),dict(date='2026-07-30',equity='22000',shares=1)]
  result=measure(rows,'2024-12-31')
  self.assertTrue(result['calendar_periods']['2026']['partial'])
  self.assertEqual(result['excluding_2026']['terminal'],21000)
  self.assertIsNone(result['turnover']['gross_traded_notional'])
  self.assertIsNone(result['turnover']['annualized_gross_turnover'])

if __name__=='__main__':unittest.main()
