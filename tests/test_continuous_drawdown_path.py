import unittest
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from fractions import Fraction as F
from scripts.audit_continuous_drawdown_path import drawdown_dates, audit


class DrawdownPathTests(unittest.TestCase):
    def test_book_not_bound_to_review_is_rejected(self):
        with TemporaryDirectory() as folder:
            book=Path(folder)/'book.json'; review=Path(folder)/'review.json'
            book.write_text('{}')
            review.write_text(json.dumps(dict(status='EXECUTED_PREFIX_REVIEW_PASS',
                proof=dict(risk_provider_certified=True),source_hashes={str(book):'0'*64})))
            with self.assertRaisesRegex(ValueError,'REVIEW_BOOK_HASH_MISMATCH'):
                audit(book,review)

    def test_unrecovered_is_not_zero_recovery_time(self):
        result=drawdown_dates([('a',F(100)),('b',F(120)),('c',F(90)),('d',F(110))])
        self.assertEqual(result['maximum_drawdown'],'1/4')
        self.assertEqual((result['peak_date'],result['trough_date']),('b','c'))
        self.assertIsNone(result['recovery_sessions_from_peak'])

    def test_recovery_uses_first_return_to_peak(self):
        result=drawdown_dates([('a',F(100)),('b',F(80)),('c',F(100)),('d',F(120))])
        self.assertEqual(result['recovery_date'],'c')
        self.assertEqual(result['recovery_sessions_from_peak'],2)

    def test_peak_tie_uses_latest_equal_peak(self):
        result=drawdown_dates([('a',F(100)),('b',F(100)),('c',F(70))])
        self.assertEqual(result['peak_date'],'b')


if __name__=='__main__':unittest.main()
