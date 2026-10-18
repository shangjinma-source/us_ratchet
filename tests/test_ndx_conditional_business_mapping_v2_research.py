from copy import deepcopy
import unittest
from backtest import ndx_conditional_business_mapping_v2_research as module


class AddendumMappingTests(unittest.TestCase):
    def fixture(self):
        old=dict(document_id='new',issuer_id='issuer',raw_path='raw',raw_sha256='bound',source_available_date='2023-01-01',excerpt=None)
        ready=deepcopy(old);ready['excerpt']=dict(section_text='Business content',section_text_sha256=module.previous._sha(b'Business content'))
        proposal=dict(document_id='new',issuer_id='issuer',raw_sha256='bound',source_available_date='2023-01-01',
            paragraph_offset=0,paragraph_characters=16,paragraph_sha256=module.previous._sha(b'Business content'),suggested_risk_chain='consumer')
        review=dict(document_id='new',issuer_id='issuer',suggested_chain='consumer',paragraph_sha256=proposal['paragraph_sha256'],
            eligible_for_conditional_research_mapping=True,independent_business_definition_match=True)
        return {'new':old},{},{},[ready],[proposal],[review]

    def test_extend_without_mutating_original(self):
        args=self.fixture();before=deepcopy(args)
        docs,props,approved=module._merge_addendum(*args)
        self.assertEqual(args,before);self.assertEqual(approved,{'new':'consumer'})
        self.assertEqual(len(docs),1);self.assertEqual(len(props),1)

    def test_existing_ready_document_never_replaced(self):
        args=self.fixture();args[0]['new']['excerpt']=deepcopy(args[3][0]['excerpt'])
        with self.assertRaisesRegex(ValueError,'Cannot replace'):module._merge_addendum(*args)

    def test_unreviewed_or_pending_not_promoted(self):
        args=self.fixture();args[5][0]['eligible_for_conditional_research_mapping']=False
        self.assertEqual(module._merge_addendum(*args)[2],{})
        args=self.fixture();args[5].clear()
        with self.assertRaisesRegex(ValueError,'Missing independent review'):module._merge_addendum(*args)

    def test_raw_identity_date_or_review_chain_mismatch(self):
        for field in ('issuer_id','raw_sha256','source_available_date'):
            args=self.fixture();args[3][0][field]='changed'
            with self.assertRaises(ValueError):module._merge_addendum(*args)
        args=self.fixture();args[5][0]['suggested_chain']='healthcare'
        with self.assertRaises(ValueError):module._merge_addendum(*args)

    def test_section_tamper_duplicate_and_unknown_document_rejected(self):
        args=self.fixture();args[3][0]['excerpt']['section_text']='forged'
        with self.assertRaises(ValueError):module._merge_addendum(*args)
        args=self.fixture();args[3].append(deepcopy(args[3][0]))
        with self.assertRaises(ValueError):module._merge_addendum(*args)
        args=self.fixture();args[3][0]['document_id']='unknown'
        with self.assertRaises(ValueError):module._merge_addendum(*args)


if __name__=='__main__':unittest.main()
