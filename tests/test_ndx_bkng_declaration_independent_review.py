"""Independent synthetic source-connection checks; no actual declaration build."""
from copy import deepcopy
import unittest
from unittest.mock import patch
import test_ndx_bkng_conditional_identity_risk_20260925 as owner

m = owner.m


def docs():
    seed = dict(decision_id='current:BKNG', tickers=['BKNG'], status='accepted', confidence='high', risk_chain='travel_hospitality', evidence_phrase='travel service provider partners')
    saved = dict(seed, source_phrase=seed['evidence_phrase'], issuer_id='issuer:0001075531', security_ids=['security:0001075531:current_ticker:BKNG'], raw_sha256=m.BOUND['annual'][1], accession_number='0001075531-26-000009', document_url=m.URL, selection_date='2026-07-13', evidence_available_date='2026-02-18', effective_from='2026-02-18', allow_fallback=False)
    manifest = dict(content_sha256=m.BOUND['annual'][1], cik='0001075531', accession_number=saved['accession_number'], fetched_at='2026-07-15T06:38:46+00:00', fetched_at_evidence='sec_public_archive_http_200', source_locator=m.URL)
    event = dict(ticker='BKNG', raw_sha256=m.BOUND['memo'][1], cusip='09857L108', security_class='COMMON', publication_date='2026-03-02', first_adjusted_trading_date='2026-04-06', received_at_utc='2026-09-11T21:04:19.470604+00:00', point_in_time_verified=False, corporate_action_completeness_verified=False, full_provider_price_identity_binding_verified=False)
    return dict(config=dict(research_only=True, decisions=[seed]), snapshot=dict(research_only=True, source_seed_sha256=m.BOUND['config'][1], decisions=[saved]), manifest=manifest, registry=dict(events=[{}, {}, event]), taxonomy=dict(risk_chains={'travel_hospitality': {'synthetic': True}}))


class Review(unittest.TestCase):
    def test_c2_entity_and_duplicate_fields_reject_even_when_c1_correct(self):
        original = owner.html()
        offset = original.index(b'id="c-2"')
        wrong = original[:offset] + original[offset:].replace(b'0001075531', b'0000000001', 1)
        duplicate = original + b'<ix:nonNumeric name="dei:TradingSymbol" contextRef="c-2">BKNG</ix:nonNumeric>'
        for raw in (wrong, duplicate):
            with self.assertRaises(ValueError):
                m.cover_facts(raw)

    def test_late_receipts_and_original_current_ticker_cannot_change(self):
        for attack in ('review', 'annual_receipt', 'memo_receipt', 'old_sid'):
            value = docs()
            if attack == 'review': value['snapshot']['decisions'][0]['selection_date'] = '2026-02-18'
            elif attack == 'annual_receipt': value['manifest']['fetched_at'] = '2026-02-18T00:00:00+00:00'
            elif attack == 'memo_receipt': value['registry']['events'][2]['received_at_utc'] = '2026-03-02T00:00:00+00:00'
            else: value['snapshot']['decisions'][0]['security_ids'] = ['security:0001075531:09857L108']
            with self.subTest(attack=attack), patch.object(m, 'sha', return_value=m.BOUND['annual'][1]), patch.object(m, 'cover_facts'), patch.object(m, 'memo_facts'):
                with self.assertRaises(ValueError): m.assemble(value, b'synthetic', [])

    def test_condition_preserves_original_rows_and_no_proof_upgrade(self):
        value = docs()
        before = deepcopy(value)
        with patch.object(m, 'sha', return_value=m.BOUND['annual'][1]), patch.object(m, 'cover_facts', return_value={}), patch.object(m, 'memo_facts', return_value={}):
            result = m.assemble(value, b'synthetic', [])
        self.assertEqual(value, before)
        self.assertEqual(result['saved_review_decision'], before['snapshot']['decisions'][0])
        self.assertTrue(result['cross_document_identity_link_is_assumption'])
        self.assertTrue(result['saved_current_ticker_is_not_dated_identity'])
        self.assertTrue(all(result[key] is False for key in m.FALSE))


if __name__ == '__main__':
    unittest.main()
