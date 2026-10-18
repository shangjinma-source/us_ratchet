"""Pure metadata transformations and attacks; no build/publish or PDF reread."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_new_cutoff_identity_risk_wiring_v6_20260925 as m

class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.saved={}
        for role in m.BOUND:
            r=m.ref(role);blob=Path(r['path']).read_bytes();assert m.sha(blob)==r['sha256']
            cls.saved[role]=m.loads(blob)

    def docs(self):return deepcopy(self.saved)

    def test_ctas_only_original100_five_sidecars_preserved(self):
        docs=self.docs();out=m.assemble(docs);old=docs['parent_wiring']
        self.assertEqual(m.canonical([r for r in out['rows'] if r['ticker']!='CTAS']),m.canonical([r for r in old['rows'] if r['ticker']!='CTAS']))
        for key in m.SIDECARS:self.assertEqual(out[key],old[key])
        self.assertEqual((out['candidate_security_count'],out['candidate_issuer_count'],out['bounded_source_missing_count']),(25,24,76))
        self.assertIsNone(out['fit_column_count']);self.assertFalse(out['typed_panel_rebuilt'])
        side=out['v6_extended_provenance'][0]
        self.assertEqual(side['original_row'],old['rows'][7]);self.assertIsNone(side['original_row']['coordinate'])
        self.assertEqual(side['complete_increment_evidence'],docs['ctas_declaration'])
        self.assertEqual(side['publication_date'],'2024-08-21');self.assertTrue(side['printed_memo_date_is_not_joint_availability'])
        self.assertEqual(docs,self.saved)

    def test_printed_memo_and_multipart_not_joint_availability(self):
        for attack in ('publication','role','oldnull','part','raw'):
            docs=self.docs();d=docs['ctas_declaration']
            if attack=='publication':d['complete_memo_evidence']['publication_date']=d['memo_received_at']
            elif attack=='role':d['complete_memo_evidence']['publication_date_role']='JOINT_AVAILABLE'
            elif attack=='oldnull':d['registry_event']['cusip']='172908105'
            elif attack=='part':d['complete_capture_evidence']['original_extraction']['part_count']=2
            else:d['complete_capture_evidence']['original_body_is_pdf_without_multipart']=True
            with self.subTest(attack=attack),self.assertRaises(ValueError):m.assemble(docs)

    def test_coordinate_late_date_and_permissions(self):
        for key,value in [('cusip','wrong'),('risk_chain','automotive'),('early_window_local_evidence_available',True),('point_in_time_verified',True),('memo_received_at','2024-08-21'),('saved_review_selection_date','2026-02-27')]:
            docs=self.docs();docs['ctas_declaration'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):m.assemble(docs)

    def test_crwd_and_denominator_not_silently_upgraded(self):
        docs=self.docs();next(r for r in docs['parent_wiring']['rows'] if r['ticker']=='CRWD')['independent_channel_detail']['liquidity_status']='READY'
        with self.assertRaises(ValueError):m.assemble(docs)
        docs=self.docs();docs['parent_wiring']['rows'].pop()
        with self.assertRaises(ValueError):m.assemble(docs)

    def test_original_row_cannot_already_be_assembled(self):
        docs=self.docs();docs['parent_wiring']['rows'][7]['coordinate']=m.COORDINATE
        with self.assertRaises(ValueError):m.assemble(docs)

    def test_publish_existing_namespace_fails_before_build(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(m,'OUTPUT',Path(directory)/'wiring.json'),patch.object(m,'build') as build:
            with self.assertRaises(ValueError):m.publish()
            build.assert_not_called()
        with patch.object(m,'LOADED_SHA','f'*64):
            with self.assertRaises(ValueError):m.guard({})

if __name__=='__main__':unittest.main()
