from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from backtest import ndx_conditional_business_mapping_research as module


class ConditionalMappingTests(unittest.TestCase):
    def fixture(self):
        candidates = [dict(security_id='s1', issuer_id='i1', ticker='A', local_risk_chain_evidence=['legacy']),
                      dict(security_id='s2', issuer_id='i1', ticker='B', local_risk_chain_evidence=['legacy']),
                      dict(security_id='s3', issuer_id='i2', ticker='C', local_risk_chain_evidence=[])]
        dates = [dict(coordinate={'selection_date':'2023-04-03'}, decision_cutoff='2023-03-31', candidates=candidates)]
        documents = {'d1':dict(document_id='d1',issuer_id='i1',source_available_date='2023-03-30')}
        proposals = {'d1':dict(suggested_risk_chain='memory')}
        return dates, documents, proposals, {'d1':'memory'}

    def test_full_denominator_same_issuer_and_no_old_field_changes(self):
        args = self.fixture()
        original = deepcopy(args[0])
        dates, audit = module._assemble(*args)
        self.assertEqual(args[0], original)
        self.assertEqual(len(dates[0]['candidates']),3)
        self.assertEqual([r['conditional_business_chain'] for r in dates[0]['candidates']],['memory','memory',None])
        for old, new in zip(original[0]['candidates'],dates[0]['candidates']):
            self.assertEqual({k:v for k,v in new.items() if k!='conditional_business_chain'},old)
        self.assertEqual(audit[0]['complete_issuer_denominator'],2)

    def test_future_publication_uses_cutoff_not_execution(self):
        dates, docs, props, approved = self.fixture()
        docs['d1']['source_available_date']='2023-04-03'
        mapped,_ = module._assemble(dates,docs,props,approved)
        self.assertTrue(all(r['conditional_business_chain'] is None for r in mapped[0]['candidates']))

    def test_missing_approval_conflict_and_unreviewed_document_retained(self):
        dates,docs,props,approved=self.fixture()
        mapped,_=module._assemble(dates,docs,props,{})
        self.assertIsNone(mapped[0]['candidates'][0]['conditional_business_chain'])
        docs['d2']=dict(document_id='d2',issuer_id='i1',source_available_date='2023-01-01')
        props['d2']=dict(suggested_risk_chain='analog_power')
        approved['d2']='analog_power'
        mapped,audit=module._assemble(dates,docs,props,approved)
        self.assertEqual(audit[0]['issuer_resolutions'][0]['status'],'UNKNOWN_CONFLICTING_APPROVED_CHAINS')
        self.assertIsNone(mapped[0]['candidates'][0]['conditional_business_chain'])
        props.pop('d2');approved.pop('d2')
        mapped,audit=module._assemble(dates,docs,props,approved)
        self.assertEqual(audit[0]['issuer_resolutions'][0]['status'],'UNKNOWN_ADDITIONAL_DOCUMENT_REVIEW_INCOMPLETE')

    def test_duplicate_sid_and_issuer_change_rejected(self):
        args=self.fixture()
        args[0][0]['candidates'].append(deepcopy(args[0][0]['candidates'][0]))
        with self.assertRaises(ValueError):module._assemble(*args)
        args=self.fixture();args[0].append(deepcopy(args[0][0]))
        args[0][1]['candidates'][0]['issuer_id']='changed'
        with self.assertRaises(ValueError):module._assemble(*args)

    def test_rehashed_self_approval_cannot_replace_external_digest(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'review.json'
            raw=json.dumps({'approved':False}).encode();path.write_bytes(raw)
            trusted=module._sha(raw)
            forged={'approved':True};forged['self_sha256']=module._sha(json.dumps(forged).encode())
            path.write_text(json.dumps(forged))
            with self.assertRaises(ValueError):module._read_bound(path,trusted)


if __name__=='__main__':unittest.main()
