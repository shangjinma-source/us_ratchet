import unittest
from fractions import Fraction
from scripts.research.evaluate_roa_complete_account_20261106 import compare, metrics


class CompleteEvaluationTests(unittest.TestCase):
    def test_incomplete_never_emits_partial_performance(self):
        result=compare(dict(status='BLOCKED',reason={'date':'2024-02-15'}),dict(book={'status':'COMPLETE'}))
        self.assertEqual(result['status'],'INCOMPLETE_METRICS_WITHHELD')
        self.assertFalse(result['economic_pass'])
        self.assertNotIn('candidate',result)

    def test_complete_label_cannot_hide_missing_sessions(self):
        book=dict(status='COMPLETE',daily_ledger=[{'date':'2026-07-30'}])
        with self.assertRaisesRegex(ValueError,'FULL_SESSION_PATH_MISMATCH'):
            compare(book,dict(book=book))

    def test_drawdown_uses_peak_not_initial_capital(self):
        book=dict(initial_cash='20000',order_log=[{},{}],daily_ledger=[
            dict(date='2021-01-04',equity='22000',cash='0'),
            dict(date='2021-06-01',equity='16000',cash='0'),
            dict(date='2021-12-31',equity='24000',cash='0')])
        result=metrics(book,'2020-12-31')
        self.assertEqual(Fraction(result['drawdown_exact']),Fraction(3,11))
        self.assertEqual(result['longest_underwater_sessions'],1)
        self.assertEqual(result['annual'][0]['return_pct'],20)
        self.assertEqual(result['fills'],2)


if __name__=='__main__':unittest.main()
