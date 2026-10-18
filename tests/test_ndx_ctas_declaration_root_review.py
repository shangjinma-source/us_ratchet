"""Independent source-boundary attacks; no declaration build or publish."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import ndx_ctas_conditional_identity_risk_20260925 as subject


class Tests(unittest.TestCase):
    def cover(self):
        fields = [('EntityCentralIndexKey', '0000723254'), ('EntityRegistrantName', 'Cintas Corporation'),
                  ('TradingSymbol', 'CTAS'), ('Security12bTitle', 'Common stock, no par value')]
        facts = ''.join(f'<ix:nonNumeric name="dei:{key}" contextRef="c-1">{value}</ix:nonNumeric>' for key, value in fields)
        context = '<xbrli:context id="c-1"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">0000723254</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2024-06-01</xbrli:startDate><xbrli:endDate>2025-05-31</xbrli:endDate></xbrli:period></xbrli:context>'
        return (context + facts + '<p>uniforms, mats, mops, shop towels</p>').encode()

    def test_cover_context_identity_not_just_matching_ticker(self):
        value = self.cover()
        self.assertEqual(subject.cover_facts(value)['entity_cik'], '0000723254')
        for changed in (value.replace(b'contextRef="c-1"', b'contextRef="other"', 1),
                        value.replace(b'2025-05-31', b'2026-05-31'),
                        value.replace(b'Common stock, no par value', b'Preferred stock'),
                        value.replace(b'</xbrli:entity>', b'<xbrldi:explicitMember>Subsidiary</xbrldi:explicitMember></xbrli:entity>')):
            with self.assertRaises(ValueError):
                subject.cover_facts(changed)

    def test_disclaimer_and_identity_are_page_specific(self):
        first = 'August 21, 2024 #55082 100 Cintas Corporation (CTAS) Common Shares CUSIP:172908105 09/12/2024 4 for 1 stock split'
        pages = [first, 'table', 'unofficial summary', 'tail']
        self.assertEqual(subject.memo_facts(pages)['disclaimer_page'], 3)
        for changed in ([first.replace('172908105', '000000000'), '172908105', pages[2], pages[3]],
                        [first, pages[2], 'table', pages[3]], pages[:3]):
            with self.assertRaises(ValueError):
                subject.memo_facts(changed)

    def test_existing_namespace_and_loaded_source_conflict_reject(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(subject, 'OUTPUT', Path(folder) / 'declaration.json'), patch.object(subject, 'build') as build:
            with self.assertRaises(ValueError):
                subject.publish()
            build.assert_not_called()
        key = next(iter(subject.LOADED))
        with self.assertRaises(ValueError):
            subject.guard({key: '0' * 64})


if __name__ == '__main__':
    unittest.main()
