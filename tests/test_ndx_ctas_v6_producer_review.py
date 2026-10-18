"""Bounded producer attacks; metadata and mocked CTAS values only."""
from copy import deepcopy
import unittest
from unittest.mock import patch
import test_ndx_new_cutoff_typed_panel_v6_independent_readback_20260925 as fixture
m=fixture.producer
class Review(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.Review.setUpClass();cls.docs=fixture.Review.docs;cls.numbers=fixture.Review.numbers
    def test_late_receipt_multipart_and_class_before_numbers(self):
        for attack in ('late','multipart','class'):
            docs=deepcopy(self.docs);d=docs['wiring']['v6_extended_provenance'][0]['complete_increment_evidence']
            if attack=='late':d['memo_received_at']='2024-08-21'
            elif attack=='multipart':d['complete_capture_evidence']['original_body_is_pdf_without_multipart']=True
            else:
                d['coordinate']['security_class']='Notes'
                next(r for r in docs['wiring']['rows'] if r['ticker']=='CTAS')['coordinate']['security_class']='Notes'
            with self.subTest(attack=attack),patch.object(m.core,'channel_values') as numbers:
                with self.assertRaises(ValueError):m.assemble(docs)
                numbers.assert_not_called()
    def test_v6_selector_and_same_issuer_classes(self):
        with patch.object(m.core,'channel_values',return_value=self.numbers):value=m.assemble(self.docs)
        panel=m.codec.typed_decode(value['panel'])
        selected=panel['universe'][panel['universe']['ticker'].isin(['GOOG','GOOGL'])]['security_id'].tolist()
        self.assertEqual(len(selected),2)
        with self.assertRaises(ValueError):m.selected_mapping_v6(panel,selected)
        panel['schema']='LATEST_CONDITIONAL_TYPED_PANEL_V5'
        with self.assertRaises(ValueError):m.selected_mapping_v6(panel,[selected[0]])
    def test_existing_namespace_before_build(self):
        with patch.object(m.Path,'exists',return_value=True),patch.object(m,'build') as build:
            with self.assertRaises(ValueError):m.publish()
            build.assert_not_called()
if __name__=='__main__':unittest.main()
