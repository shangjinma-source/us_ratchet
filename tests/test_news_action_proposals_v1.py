import unittest
from hashlib import sha256

from scripts.research.propose_news_actions_v1 import public_record, validate_answer


class NewsActionProposalTests(unittest.TestCase):
    def setUp(self):
        self.text = 'Reported revenue rose.\nAn export restriction creates uncertainty.'
        self.row = dict(id='MRNA_Q2', source_url='https://example.test/report',
            text_hash=sha256(self.text.encode()).hexdigest(), text=self.text,
            empty_text_pages=[], account={'cash': 123}, future_return='must not project')
        self.answer = dict(id='MRNA_Q2', action='BLOCK_NEW_BUYS', assessment='JUDGMENT',
            evidence_quotes=['An export restriction creates uncertainty.'], rationale='Research only',
            counterevidence='Revenue rose', uncertainty='Duration unknown', temporal_scope='Unclear')

    def test_projection_excludes_account_and_outcome(self):
        result = public_record({'records': [self.row]}, 'MRNA_Q2')
        self.assertEqual(set(result), {'id', 'source_url', 'text_hash', 'text', 'empty_text_pages'})
        self.row['text'] += 'modified'
        with self.assertRaisesRegex(ValueError, 'HASH'):
            public_record({'records': [self.row]}, 'MRNA_Q2')

    def test_quote_binding_and_wrong_case(self):
        validate_answer(self.answer, self.row)
        self.answer['evidence_quotes'] = ['Invented insolvency.']
        with self.assertRaisesRegex(ValueError, 'QUOTE'):
            validate_answer(self.answer, self.row)
        self.answer['id'] = 'APP_Q3'
        with self.assertRaisesRegex(ValueError, 'CASE_ID'):
            validate_answer(self.answer, self.row)

    def test_abstention_cannot_exit_or_be_judgment_without_evidence(self):
        self.answer.update(assessment='ABSTAIN', action='EXIT', evidence_quotes=[])
        with self.assertRaisesRegex(ValueError, 'ABSTENTION'):
            validate_answer(self.answer, self.row)
        self.answer.update(assessment='JUDGMENT', action='NO_CHANGE')
        with self.assertRaisesRegex(ValueError, 'EVIDENCE'):
            validate_answer(self.answer, self.row)


if __name__ == '__main__':
    unittest.main()
