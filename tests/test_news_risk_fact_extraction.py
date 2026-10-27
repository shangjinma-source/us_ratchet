"""Evidence and input isolation checks; not a model accuracy benchmark."""
from copy import deepcopy
from hashlib import sha256
import unittest

from scripts.research.extract_news_risk_facts_v1 import validate_input, validate_output


class NewsFactExtractionTests(unittest.TestCase):
    def setUp(self):
        self.text = 'Deliveries may be delayed into the following year.'
        self.payload = {'records': [dict(id='public', url='https://issuer.example/release',
            text=self.text, text_sha256=sha256(self.text.encode()).hexdigest(),
            content_kind='COMPLETE_PUBLIC_ANNOUNCEMENT', account={'cash': 'private'})]}
        self.result = {'records': [dict(id='public', classification='TEMPORARY_DELIVERY_CONSTRAINT',
            year='FY2021', product='vaccine', dose='100ug', evidence_quote=self.text, uncertainty='test')]}

    def test_only_bound_public_fields_enter_prompt(self):
        public = validate_input(self.payload)
        self.assertNotIn('account', public[0])
        self.payload['records'][0]['text'] += 'tampered'
        with self.assertRaisesRegex(ValueError, 'SOURCE_TEXT_HASH_MISMATCH'):
            validate_input(self.payload)

    def test_fabricated_quote_or_wrong_id_rejected(self):
        public = validate_input(self.payload)
        for field, value, error in [('evidence_quote', 'Production is fully restored.', 'EXACT_QUOTE'),
                                    ('id', 'different', 'RECORD_IDS')]:
            altered = deepcopy(self.result)
            altered['records'][0][field] = value
            with self.assertRaisesRegex(ValueError, error):
                validate_output(altered, public)

    def test_insufficient_evidence_is_unknown_not_trade_instruction(self):
        public = validate_input(self.payload)
        for field in ('evidence_quote', 'year', 'product', 'dose'):
            altered = deepcopy(self.result)
            altered['records'][0][field] = ''
            self.assertEqual(validate_output(altered, public)['records'][0]['classification'], 'UNKNOWN')


if __name__ == '__main__':
    unittest.main()
