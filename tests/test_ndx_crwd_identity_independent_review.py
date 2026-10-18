"""Independent CRWD relation attacks; no actual build or publish."""
from copy import deepcopy
import unittest
from pathlib import Path
import tempfile
from unittest.mock import patch
import test_ndx_crwd_conditional_identity_20260923 as fixture

m=fixture.m


class IndependentCrwdReview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.CrwdTests.setUpClass()
        f=fixture.CrwdTests
        cls.args=dict(cover_bytes=f.cover,memo_text=f.memo,suggestion=f.suggestion,review=f.review,channel=f.channel)

    def test_memo_after_window_start_does_not_backdate_availability(self):
        value=m.relation(**self.args)
        self.assertGreater(value['memo_publication_date'],value['calendar'][0])
        self.assertFalse(value['evidence_available_before_window_start'])
        self.assertFalse(value['direct_single_document_cusip_cik_proof'])
        self.assertFalse(value['memo_contains_subject_cik'])
        self.assertFalse(value['classification_valid_interval_verified'])
        self.assertIn('VOLUME_UNIT_UNKNOWN',value['training_blockers'])

    def test_duplicate_memo_and_conflicting_extra_cusip_are_rejected(self):
        for extra in (' #59135',' CUSIP:22788C104'):
            args=dict(self.args,memo_text=self.args['memo_text']+extra)
            with self.assertRaises(ValueError):m.relation(**args)

    def test_cross_document_subject_and_business_excerpt_cannot_be_replaced(self):
        for attack in ('subject','excerpt','interval'):
            args=deepcopy(self.args)
            if attack=='subject':args['suggestion']['document_id']='issuer:0001535527:OTHER'
            elif attack=='excerpt':args['suggestion']['excerpt_sha256']='0'*64
            else:args['review']['classification_interval_verified']=True
            with self.subTest(attack=attack),self.assertRaises(ValueError):m.relation(**args)

    def test_volume_or_calendar_gap_cannot_be_hidden(self):
        for attack in ('volume','short','first'):
            args=deepcopy(self.args);ci=args['channel']['channel_input']
            if attack=='volume':ci['liquidity']['status']='CONDITIONAL_RAW_VOLUME_TIMES_NOMINAL_CLOSE'
            elif attack=='short':ci['calendar'].pop(50)
            else:ci['calendar'][0]='2026-03-19'
            with self.subTest(attack=attack),self.assertRaises(ValueError):m.relation(**args)

    def test_consumed_blob_hash_is_checked_even_when_disk_guard_was_passed(self):
        with patch.object(m,'check'),patch.object(m.Path,'read_bytes',return_value=b'changed'),patch.object(m,'relation') as relation:
            with self.assertRaises(ValueError):m.build()
            relation.assert_not_called()

    def test_no_arbitrary_payload_and_existing_namespace_stops_before_build(self):
        with self.assertRaises(TypeError):m.build_and_publish({'risk_chain':'forged'})
        with tempfile.TemporaryDirectory() as directory,patch.object(m,'OUTPUT',Path(directory)/'identity.json'),patch.object(m,'build') as build:
            with self.assertRaises(ValueError):m.build_and_publish()
            build.assert_not_called()


if __name__=='__main__':unittest.main()
