"""CTAS synthetic-only increment; saved parents read as metadata."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_new_cutoff_conditional_panel_v6_20260925 as m

class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.docs={k:m.codec.loads((m.BASE/p).read_bytes()) for k,(p,h) in m.BOUND.items()}
        cls.numbers=([.01]*126,[20.]*127,dict(volumes=[10000000]*63,dollars=[200000000.]*63,median=200000000.),None)
    def test_all_hard_anchors_and_metadata(self):
        for p,h in m.BOUND.values():self.assertEqual(m.sha((m.BASE/p).read_bytes()),h)
        self.assertEqual(len(m.validate_sources(self.docs)),127)
    def test_single_mock_increment_and_five_old_sidecars(self):
        with patch.object(m.core,'channel_values',return_value=self.numbers) as call:value=m.assemble(self.docs)
        self.assertEqual(call.call_count,1);self.assertEqual(call.call_args.args[2],'CTAS')
        self.assertEqual((value['actual_panel_security_count'],value['actual_panel_issuer_count']),(24,23))
        for key in ('original_evidence_and_projection','incremental_evidence_and_projection','v3_incremental_evidence_and_projection','v4_incremental_evidence_and_projection','v5_incremental_evidence_and_projection'):
            self.assertEqual(value[key],self.docs['parent_panel'][key])
        self.assertTrue(all(p['exact'] for p in value['original23_frame_exact_proof'].values()))
        self.assertEqual(value['v6_incremental_evidence_and_projection'][0]['publication_date'],'2024-08-21')
    def test_late_receipt_and_multipart_attacks_before_numbers(self):
        for attack in ('early','receipt','multipart','registry'):
            docs=deepcopy(self.docs);d=docs['wiring']['v6_extended_provenance'][0]['complete_increment_evidence']
            if attack=='early':d['early_window_local_evidence_available']=True
            elif attack=='receipt':d['memo_received_at']='2026-03-01'
            elif attack=='multipart':d['complete_capture_evidence']['original_body_is_pdf_without_multipart']=True
            else:d['registry_event']['cusip']='172908105'
            with self.subTest(attack=attack),patch.object(m.core,'channel_values') as calc,self.assertRaises(ValueError):m.assemble(docs)
            calc.assert_not_called()
    def test_blocked_ctas_not_forced(self):
        numbers=list(self.numbers);numbers[2]=None;numbers[3]='BLOCKED'
        with patch.object(m.core,'channel_values',return_value=numbers),self.assertRaises(ValueError):m.assemble(self.docs)
    def test_old_cell_and_class_preserved(self):
        before=m.codec.typed_decode(self.docs['parent_panel']['panel'])
        for attack in ('cell','dtype'):
            after=deepcopy(before);ticker=after['returns'].columns[0]
            if attack=='cell':after['returns'].iloc[0,0]=.9
            else:after['raw_volume'][ticker]=after['raw_volume'][ticker].astype('float64')
            with self.assertRaises(ValueError):m.original_frame_proof(before,after)
    def test_namespace_guard(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(m,'OUTPUT',Path(directory)/'panel.json'),patch.object(m,'build') as build:
            with self.assertRaises(ValueError):m.publish()
            build.assert_not_called()
    def test_v6_mapping_rejects_duplicate_issuer_and_old_schema(self):
        with patch.object(m.core,'channel_values',return_value=self.numbers):value=m.assemble(self.docs)
        panel=m.codec.typed_decode(value['panel'])
        by={row['ticker']:row['security_id'] for row in panel['universe'].to_dict('records')}
        self.assertEqual(len(m.selected_mapping_v6(panel,[by['CTAS']])),1)
        with self.assertRaises(ValueError):m.selected_mapping_v6(panel,[by['GOOG'],by['GOOGL']])
        panel['schema']='LATEST_CONDITIONAL_TYPED_PANEL_V5';panel['panel_content_sha256']=m.core.panel_digest(panel)
        with self.assertRaises(ValueError):m.selected_mapping_v6(panel,[by['CTAS']])

if __name__=='__main__':unittest.main()
