"""Pure metadata transformations and attacks; no build/publish or PDF reread."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_new_cutoff_identity_risk_wiring_v5_20260925 as m

class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.saved={}
        for role in m.BOUND:
            r=m.ref(role);blob=Path(r['path']).read_bytes();assert m.sha(blob)==r['sha256']
            cls.saved[role]=m.loads(blob)

    def docs(self):return deepcopy(self.saved)

    def test_orly_only_original100_four_sidecars_preserved(self):
        docs=self.docs();out=m.assemble(docs);old=docs['parent_wiring']
        self.assertEqual(m.canonical([r for r in out['rows'] if r['ticker']!='ORLY']),m.canonical([r for r in old['rows'] if r['ticker']!='ORLY']))
        for key in m.SIDECARS:self.assertEqual(out[key],old[key])
        self.assertEqual((out['candidate_security_count'],out['candidate_issuer_count'],out['bounded_source_missing_count']),(24,23,77))
        self.assertIsNone(out['fit_column_count']);self.assertFalse(out['typed_panel_rebuilt'])
        side=out['v5_extended_provenance'][0]
        self.assertEqual(side['original_row'],old['rows'][27]);self.assertIsNone(side['original_row']['coordinate'])
        self.assertEqual(side['complete_increment_evidence'],docs['orly_declaration'])
        self.assertIsNone(side['publication_date']);self.assertFalse(side['action_or_signature_date_used_as_publication'])
        self.assertEqual(docs,self.saved)

    def test_action_signature_not_publication_or_textparser(self):
        for attack in ('publication','visualpub','parser','faq','occ'):
            docs=self.docs();d=docs['orly_declaration']
            if attack=='publication':d['publication_date']=d['action_date']
            elif attack=='visualpub':d['complete_visual_transcription']['publication_date']='2025-06-09'
            elif attack=='parser':d['complete_visual_transcription']['visual_transcription_is_not_text_parser_output']=False
            elif attack=='faq':d['original_faq_registry_event']['cusip']='67103H107'
            else:d['complete_capture_evidence']['occ_receipt']['http_status']=200
            with self.subTest(attack=attack),self.assertRaises(ValueError):m.assemble(docs)

    def test_coordinate_late_date_and_permissions(self):
        for key,value in [('cusip','wrong'),('risk_chain','industrial'),('early_window_local_evidence_available',True),('point_in_time_verified',True),('form_received_at','2025-06-09'),('saved_review_selection_date','2026-02-27')]:
            docs=self.docs();docs['orly_declaration'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):m.assemble(docs)

    def test_crwd_and_denominator_not_silently_upgraded(self):
        docs=self.docs();next(r for r in docs['parent_wiring']['rows'] if r['ticker']=='CRWD')['independent_channel_detail']['liquidity_status']='READY'
        with self.assertRaises(ValueError):m.assemble(docs)
        docs=self.docs();docs['parent_wiring']['rows'].pop()
        with self.assertRaises(ValueError):m.assemble(docs)

    def test_original_row_cannot_already_be_assembled(self):
        docs=self.docs();docs['parent_wiring']['rows'][27]['coordinate']=m.COORDINATE
        with self.assertRaises(ValueError):m.assemble(docs)

    def test_publish_existing_namespace_fails_before_build(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(m,'OUTPUT',Path(directory)/'wiring.json'),patch.object(m,'build') as build:
            with self.assertRaises(ValueError):m.publish()
            build.assert_not_called()
        with patch.object(m,'LOADED_SHA','f'*64):
            with self.assertRaises(ValueError):m.guard({})

if __name__=='__main__':unittest.main()
