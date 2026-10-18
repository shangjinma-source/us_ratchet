"""Independent ORLY source boundaries; no actual declaration assembly."""
from copy import deepcopy
import unittest
from scripts import ndx_orly_conditional_identity_risk_20260925 as module


def annual():
    context = '<xbrli:context id="' + module.CONTEXT + '"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">0000898173</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2025-01-01</xbrli:startDate><xbrli:endDate>2025-12-31</xbrli:endDate></xbrli:period></xbrli:context>'
    fields = ''.join('<ix:nonNumeric name="' + name + '" contextRef="' + module.CONTEXT + '">' + value + '</ix:nonNumeric>' for name, value in [('dei:EntityCentralIndexKey', '0000898173'), ('dei:Security12bTitle', 'Common Stock'), ('dei:TradingSymbol', 'ORLY')])
    return (context + fields + ' specialty retailers of automotive aftermarket parts').encode()


class Review(unittest.TestCase):
    def test_tax_number_or_mixed_cover_context_cannot_replace_cik(self):
        self.assertEqual(module.cover_facts(annual())['entity_cik'], '0000898173')
        for blob in (annual().replace(b'0000898173', b'27-4358837', 1), annual().replace(b'contextRef="' + module.CONTEXT.encode() + b'"', b'contextRef="other"', 1)):
            with self.assertRaises(ValueError):
                module.cover_facts(blob)

    def test_visual_facts_keep_printed_cusip_and_no_publication(self):
        keys = ('form_pdf', 'page1', 'page2', 'root_visual_review', 'source_lead', 'capture_readback')
        blobs = {key: module.BOUND[key][0].read_bytes() for key in keys}
        facts = module.visual_facts(blobs, ['', ''])
        self.assertEqual((facts['cusip_original_text'], facts['cusip']), ('67103H 107', '67103H107'))
        self.assertIsNone(facts['publication_date'])
        self.assertFalse(facts['publication_date_verified'])
        self.assertTrue(facts['visual_transcription_is_not_text_parser_output'])
        self.assertFalse(facts['form_contains_cik_verified'])
        self.assertFalse(facts['ein_used_as_cik'])
        with self.assertRaises(ValueError):
            module.visual_facts(blobs, ['machine text', ''])
        changed = deepcopy(blobs)
        changed['page1'] += b'changed'
        with self.assertRaises(ValueError):
            module.visual_facts(changed, ['', ''])

    def test_all_hard_anchors_match_current_bytes_without_build(self):
        self.assertEqual(len(module.BOUND), 20)
        for key, (path, expected) in module.BOUND.items():
            with self.subTest(key=key):
                self.assertEqual(module.sha(path.read_bytes()), expected)


if __name__ == '__main__':
    unittest.main()
