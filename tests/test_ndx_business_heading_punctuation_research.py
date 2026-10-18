import unittest

from backtest import ndx_business_heading_excerpt_research as original
from backtest.ndx_business_heading_punctuation_research import extract_business_heading_punctuation


class PunctuationTests(unittest.TestCase):
    def document(self, start, end):
        return ('<html><head><meta charset="utf-8"></head><body><p>'+start+'</p><p>'+('A substantial product business description. '*20)+
                ' See Part I, Item 1A. Risk Factors for additional details.</p><p>'+end+
                '</p><p>Outside risk section.</p></body></html>').encode()

    def test_complete_dash_and_terminal_punctuation(self):
        for start, end in [('Item 1\u2014Business', 'Item 1A\u2014Risk Factors'),
                           ('ITEM 1. BUSINESS.', 'ITEM 1A. RISK FACTORS.'),
                           ('Item 1: Business:', 'Item 1A: Risk Factors:')]:
            with self.subTest(start=start):
                result = extract_business_heading_punctuation(self.document(start, end))
                self.assertIn('additional details.', result['section_text'])
                self.assertNotIn('Outside risk section', result['section_text'])

    def test_frozen_original_not_mutated(self):
        before = (original.START.pattern, original.END.pattern)
        raw = self.document('Item 1. Business', 'Item 1A. Risk Factors')
        result = extract_business_heading_punctuation(raw)
        self.assertEqual(result['section_text'], original.extract_business_heading_excerpt(raw)['section_text'])
        self.assertEqual(before, (original.START.pattern, original.END.pattern))

    def test_prose_table_and_different_parent_still_rejected(self):
        bodies = [self.document('See Item 1. Business.', 'Item 1A. Risk Factors.'),
                  b'<html><body><table><tr><td><p>Item 1. Business.</p></td></tr></table><p>Item 1A. Risk Factors.</p></body></html>',
                  b'<html><body><div><p>Item 1. Business.</p></div><section><p>Item 1A. Risk Factors.</p></section></body></html>']
        for raw in bodies:
            with self.assertRaises(ValueError):
                extract_business_heading_punctuation(raw)


if __name__ == '__main__':
    unittest.main()
