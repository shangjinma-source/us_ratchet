"""Synthetic evidence validation only; no historical/economic result."""
import copy
from hashlib import sha256
import unittest

from scripts.research.guidance_numeric_comparator_v1 import compare_guidance


def fixture(low, high, timestamp):
    text = f'Fiscal 2026 GAAP revenue guidance is USD {low} to {high} million dollars.'
    digest = sha256(text.encode()).hexdigest()
    low_start = text.index(low, text.index('USD'))
    high_start = text.index(high, low_start + len(low))
    record = dict(issuer_cik='123', metric='revenue', currency='USD', unit_scale='1000000',
                  fiscal_period_start='2026-01-01', fiscal_period_end='2026-12-31', basis='GAAP',
                  low=low, high=high, publication_datetime=timestamp, status='FORWARD_GUIDANCE',
                  source_url='https://issuer.example/announcement/' + timestamp[:10],
                  source_sha256=digest, quote_start=0, quote_end=len(text),
                  low_span=[low_start, low_start + len(low)], high_span=[high_start, high_start + len(high)])
    source = dict(issuer_cik='123', url=record['source_url'], text=text, publication_datetime=timestamp)
    return record, {digest: source}


class GuidanceComparisonTests(unittest.TestCase):
    def setUp(self):
        self.old, sources = fixture('100', '120', '2026-02-01T12:00:00Z')
        self.new, other = fixture('90', '110', '2026-05-01T12:00:00Z')
        self.sources = {**sources, **other}

    def compare(self):
        return compare_guidance(self.old, self.new, self.sources)

    def test_ended_period_and_preliminary_actual_rejected(self):
        self.new['fiscal_period_end'] = '2026-04-30'
        self.assertEqual(self.compare()['reason'], 'NOT_FORWARD_GUIDANCE')
        self.new['fiscal_period_end'] = '2026-05-01'
        self.assertEqual(self.compare()['reason'], 'NOT_FORWARD_GUIDANCE')
        self.new['fiscal_period_end'] = '2026-12-31'
        self.new['status'] = 'PRELIMINARY_ACTUAL'
        self.assertEqual(self.compare()['reason'], 'NOT_FORWARD_GUIDANCE')

    def test_verified_strict_cut(self):
        result = self.compare()
        self.assertEqual(result['status'], 'NUMERIC_GUIDANCE_CUT_CANDIDATE')
        self.assertFalse(result['is_trading_signal'])

    def test_changed_scope_and_missing_fields(self):
        for key, value in [('issuer_cik','456'), ('metric','EPS'), ('currency','EUR'),
                           ('unit_scale','1'), ('basis','non-GAAP'),
                           ('fiscal_period_end','2027-12-31'), ('status','WITHDRAWN'), ('low',None)]:
            with self.subTest(key=key):
                record = dict(self.new, **{key:value})
                self.assertEqual(compare_guidance(self.old, record, self.sources)['status'], 'UNKNOWN')

    def test_equal_or_mixed_endpoints_not_cut(self):
        for low, high in [('90','120'), ('100','110'), ('80','130'), ('110','130')]:
            record, sources = fixture(low, high, '2026-05-01T12:00:00Z')
            self.assertEqual(compare_guidance(self.old, record, {**self.sources, **sources})['status'], 'COMPARABLE_NO_STRICT_CUT')

    def test_unchanged_and_raise_are_known_non_cuts(self):
        for low, high, expected in [('100', '120', 'UNCHANGED'), ('110', '130', 'RAISE')]:
            record, sources = fixture(low, high, '2026-05-01T12:00:00Z')
            # Identical text has an identical hash; distinguish the second document
            # with its date in the evidence body, retaining numeric span locations.
            source = next(iter(sources.values()))
            source['text'] += ' Published May 1.'
            digest = sha256(source['text'].encode()).hexdigest()
            record['source_sha256'] = digest
            result = compare_guidance(self.old, record, {**self.sources, digest: source})
            self.assertEqual(result['status'], 'COMPARABLE_NO_STRICT_CUT')
            self.assertEqual(result['reason'], expected)

    def test_reversed_time_or_missing_timezone(self):
        self.assertEqual(compare_guidance(self.new,self.old,self.sources)['reason'], 'PUBLICATION_ORDER_INVALID')
        self.new['publication_datetime'] = '2026-05-01T12:00:00'
        self.assertEqual(self.compare()['status'], 'UNKNOWN')

    def test_boolean_and_altered_source_not_evidence(self):
        self.new['provided'] = True
        self.assertEqual(compare_guidance(self.old,self.new,{})['status'], 'UNKNOWN')
        self.sources[self.new['source_sha256']]['text'] += ' altered'
        self.assertEqual(self.compare()['reason'], 'SOURCE_HASH_MISMATCH')

    def test_numeric_transcription_and_partial_token(self):
        self.new['low'] = '80'
        self.assertEqual(self.compare()['reason'], 'QUOTE_NUMERIC_MISMATCH')
        self.new['low'] = '0'
        self.new['low_span'][0] += 1
        self.assertEqual(self.compare()['reason'], 'PARTIAL_OR_UNSUPPORTED_NUMERIC_TOKEN')

    def test_exponent_substrings_cannot_create_false_cut(self):
        record, sources = fixture('1e3', '2e3', '2026-05-01T12:00:00Z')
        record.update(low='1', high='2')
        record['low_span'][1] = record['low_span'][0] + 1
        record['high_span'][1] = record['high_span'][0] + 1
        result = compare_guidance(self.old, record, {**self.sources, **sources})
        self.assertEqual(result['status'], 'UNKNOWN')
        self.assertEqual(result['reason'], 'PARTIAL_OR_UNSUPPORTED_NUMERIC_TOKEN')

    def test_quote_location_and_source_metadata(self):
        for field, value in [('url','https://other.example'), ('issuer_cik','999'),
                             ('publication_datetime','2026-05-02T12:00:00Z')]:
            sources = copy.deepcopy(self.sources)
            sources[self.new['source_sha256']][field] = value
            self.assertEqual(compare_guidance(self.old,self.new,sources)['status'], 'UNKNOWN')
        self.new['quote_end'] = self.new['low_span'][0]
        self.assertEqual(self.compare()['reason'], 'NUMBER_OUTSIDE_QUOTE')


if __name__ == '__main__':
    unittest.main()
