import unittest

from backtest.ndx_business_heading_excerpt_research import extract_business_heading_excerpt


def filing(extra=''):
    return ('<html><body><table><tr><td><div><a href="#business">ITEM 1. BUSINESS</a></div></td></tr></table>'
            '<div><span>ITEM 1.</span> <span>BUSINESS</span></div>'
            '<p>' + 'Discussion of company operations. ' * 10 + ' See Part I, Item 1A. Risk Factors for risks.</p>'
            '<div>We manufacture processor and graphics products, and provide software support.</div>'
            + extra + '<div>ITEM 1A. RISK FACTORS</div><p>END_SENTINEL.</p></body></html>').encode()


class BusinessHeadingTests(unittest.TestCase):
    def test_prose_cross_reference_does_not_truncate_business(self):
        result = extract_business_heading_excerpt(filing())
        self.assertIn('graphics products', result['section_text'])
        self.assertIn('See Part I, Item 1A.', result['section_text'])
        self.assertNotIn('END_SENTINEL', result['section_text'])
        self.assertFalse(result['risk_chain_assigned'])

    def test_duplicate_actual_heading_rejected(self):
        with self.assertRaisesRegex(ValueError, 'unambiguous'):
            extract_business_heading_excerpt(filing('<div>ITEM 1. BUSINESS</div>'))

    def test_missing_actual_boundary_and_table_only_headings_rejected(self):
        for raw in (filing().replace(b'<div>ITEM 1A. RISK FACTORS</div>', b''),
                    b'<html><body><table><tr><td><div>ITEM 1. BUSINESS</div><div>ITEM 1A. RISK FACTORS</div></td></tr></table></body></html>'):
            with self.assertRaises(ValueError):
                extract_business_heading_excerpt(raw)

    def test_hidden_markup_cannot_supply_false_duplicate(self):
        result = extract_business_heading_excerpt(filing('<ix:hidden><div>ITEM 1. BUSINESS</div></ix:hidden>'))
        self.assertIn('graphics products', result['section_text'])

    def test_plain_text_between_sibling_blocks_is_preserved(self):
        result = extract_business_heading_excerpt(filing('Additional unwrapped business detail.'))
        self.assertIn('Additional unwrapped business detail.', result['section_text'])


if __name__ == '__main__':
    unittest.main()
