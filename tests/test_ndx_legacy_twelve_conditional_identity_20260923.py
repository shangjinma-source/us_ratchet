"""Read sealed fixtures; no real build/publish, fit, or account."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_legacy_twelve_conditional_identity_20260923 as m


def documents():
    result={}
    for role in m.BOUND:
        ref=m.reference(role);raw=Path(ref['path']).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=ref['sha256']:raise AssertionError('Fixture source mismatch')
        result[role]=json.loads(raw)
    return result


class IdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.docs=documents()

    def test_exact_twelve_sid_eleven_issuer_and_original_evidence_retained(self):
        value=m.assemble(deepcopy(self.docs));by={r['ticker']:r for r in value['rows']}
        self.assertEqual((value['security_count'],value['distinct_issuer_count']),(12,11))
        self.assertEqual(len(value['calendar']),107)
        self.assertEqual([len(r['saved_candidate']['selected']) for r in value['saved_lane_choices']],[4,4,4,4,6,4])
        self.assertEqual(by['GOOG']['issuer_id'],by['GOOGL']['issuer_id'])
        self.assertNotEqual(by['GOOG']['security_id'],by['GOOGL']['security_id'])
        self.assertEqual(by['TXN']['evidence']['dated_evidence']['filing_date'],'2022-02-10')
        self.assertEqual(by['ENPH']['evidence']['original_conditional_window']['end'],'2023-05-01')
        for ticker in m.NEW:
            old=next(r for r in self.docs['facts']['rows'] if r['ticker']==ticker)
            self.assertEqual(by[ticker]['evidence']['dated_evidence'],old)
        self.assertTrue(all(value[k] is False for k in m.FALSE))

    def test_13f_subject_not_reporter_and_txn_date_not_upgraded(self):
        for attack in ('direct','reporter','txn','team'):
            docs=deepcopy(self.docs)
            row=next(r for r in docs['facts']['rows'] if r['ticker']==('TXN' if attack=='txn' else 'TEAM' if attack=='team' else 'DDOG'))
            if attack=='direct':row['subject_cik_directly_in_cusip_document']=True
            if attack=='reporter':row['subject_cik']=row['reporter_cik']
            if attack=='txn':row['filing_date']='2023-02-10'
            if attack=='team':row['local_cover_context']['issuer_name']='Atlassian plc'
            with self.subTest(attack=attack),self.assertRaises(ValueError):m.assemble(docs)

    def test_duplicate_wrong_class_and_enph_interval_rejected(self):
        for attack in ('duplicate','class','enph','permission'):
            docs=deepcopy(self.docs)
            if attack=='duplicate':docs['facts']['rows'].append(deepcopy(docs['facts']['rows'][0]))
            if attack=='class':next(r for r in docs['return_identity']['rows'] if r['ticker']=='GOOGL')['security_class']='Class C Capital Stock'
            if attack=='enph':docs['enph']['identity_projection']['enph_original_conditional_window']['end']='2023-09-01'
            if attack=='permission':docs['facts']['promotion_allowed']=True
            with self.subTest(attack=attack),self.assertRaises(ValueError):m.assemble(docs)

    def test_exact_calendar_lane_union_and_per_decision_issuer(self):
        for attack in ('calendar','selection','same_issuer'):
            docs=deepcopy(self.docs)
            if attack=='calendar':docs['prices']['calendar'].pop()
            else:
                selected=docs['lane']['decisions'][0]['lanes']['LEGACY_TARGET_DISTANCE'][0]['selected']
                sid=next(iter(selected))
                if attack=='selection':del selected[sid]
                else:selected[sid]['issuer_id']='issuer:0001652044'
            with self.subTest(attack=attack),self.assertRaises(ValueError):m.assemble(docs)

    def test_missing_hard_sha_and_existing_namespace_fail_before_build(self):
        with patch.dict(m.BOUND,{'facts':('facts.json','PENDING')}),patch.object(m.archive,'strict') as strict:
            with self.assertRaises(ValueError):m.build()
            strict.assert_not_called()
        with tempfile.TemporaryDirectory() as folder,patch.object(m,'OUTPUT',Path(folder)),patch.object(m,'build') as build:
            with self.assertRaises(ValueError):m.publish()
            build.assert_not_called()

    def test_publication_source_drift_is_not_success(self):
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)/'new';value=dict(historical_expected_source_hashes={},archive_resolution={})
            with patch.object(m,'OUTPUT',output),patch.object(m,'build',return_value=value),patch.object(m.archive,'load_contract',return_value={}), \
                    patch.object(m.archive,'strict'),patch.object(m.archive,'verify_expected_sources',side_effect=[{}, {'changed':True}]):
                with self.assertRaisesRegex(ValueError,'source drift'):m.publish()
                self.assertTrue((output/'identities.json').exists())


if __name__=='__main__':unittest.main()
