from hashlib import sha256
import unittest

from scripts.research.extract_guidance_with_codex_v1 import validate_input, validate_output


class GuidanceExtractionTests(unittest.TestCase):
    def fixture(self):
        text = 'FY2022 guidance: $4.4 billion to $4.8 billion total revenue'
        source = dict(id='a', url='https://example.com/public', text=text,
                      text_sha256=sha256(text.encode()).hexdigest())
        row = dict(id='a', status='FORWARD_GUIDANCE', low='4.4', high='4.8', unit='billion',
                   currency='USD', metric='TOTAL_REVENUE', fiscal_year='FY2022',
                   scope='FULL_FISCAL_YEAR', quote=text, uncertainty='')
        return source, row

    def test_content_hash_and_batch_bounds(self):
        source, _ = self.fixture()
        self.assertEqual(len(validate_input(dict(records=[source]))), 1)
        for records in ([], [source, source], [dict(source, text='changed')]):
            with self.assertRaises(ValueError):
                validate_input(dict(records=records))

    def test_hallucinated_or_nonunique_quote_rejected(self):
        source, row = self.fixture()
        for altered in (dict(row, quote='invented'), dict(row, low='7.2')):
            with self.assertRaises(ValueError):
                validate_output(dict(records=[altered]), [source])
        with self.assertRaises(ValueError):
            validate_output(dict(records=[row]), [dict(source, text=source['text']*2)])

    def test_unknown_is_not_forced_into_guidance(self):
        source, row = self.fixture()
        row.update(status='UNKNOWN', low='', high='', quote='', uncertainty='Incomplete text')
        self.assertEqual(validate_output(dict(records=[row]), [source])['records'][0]['status'], 'UNKNOWN')

    def test_ids_must_match_exactly(self):
        source, row = self.fixture()
        with self.assertRaises(ValueError):
            validate_output(dict(records=[dict(row, id='other')]), [source])

    def test_substring_and_exponent_are_not_valid_numeric_extraction(self):
        source, row = self.fixture()
        for low_text, high_text, low, high in [('14.4', '14.8', '4.4', '4.8'),
                                              ('1e3', '2e3', '1', '2'),
                                              ('(4.4)', '(4.8)', '4.4', '4.8')]:
            text = 'FY2022 guidance: $'+low_text+' to $'+high_text+' total revenue'
            with self.assertRaises(ValueError):
                validate_output(dict(records=[dict(row, low=low, high=high, quote=text)]), [dict(source, text=text)])


if __name__ == '__main__':
    unittest.main()
