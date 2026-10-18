from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from backtest import ndx_corrected_delta_paired_overlay_limited_research as pure
from scripts import ndx_corrected_delta_paired_overlay_limited_research as reader
from test_ndx_corrected_delta_paired_overlay_research import fixture


class LimitedOverlayTests(unittest.TestCase):
    def test_resigned_or_relocated_independent_audit_is_rejected(self):
        for path,sha in ((reader.AUDIT,'0'*64),(reader.AUDIT.with_name('resigned.json'),reader.AUDIT_SHA)):
            with self.assertRaisesRegex(ValueError,'Hard independently completed'):
                reader.build(parent_path='unused',parent_sha256='unused',index_path='unused',index_sha256='unused',audit_path=path,audit_sha256=sha)

    def test_explicit_limited_parent_preserves_unrelated_records(self):
        parent,row=fixture('ndx_corrected_base_overlay_limited_drift_v3')
        parent['historical_full_source_closure_verified']=False
        before=deepcopy(parent)
        result=pure.extend_delta_paired_overlay(parent=parent,replacements=[row],expected_tasks=[row['task']])
        self.assertEqual(parent,before)
        self.assertEqual(result['records'][1:],before['records'][1:])
        self.assertFalse(result['historical_full_source_closure_verified'])
        self.assertFalse(result['promotion_allowed'])
        self.assertEqual(result['pending_count'],2)

    def test_publication_rechecks_partition_before_and_after_write(self):
        required=dict(reader.LOADED,**{str(reader.AUDIT):reader.AUDIT_SHA})
        value=dict(schema='ndx_corrected_delta_paired_overlay_limited_drift_v2',
            historical_full_source_closure_verified=False,historical_expected_source_hashes=dict(required,old='sha'),
            verified_source_hashes=dict(required,good='sha'),historical_price_cache_gap_observations=[{'gap':True}],
            historical_loader_gap_observations=[{'yaml':True}])
        good=dict(verified_source_hashes=value['verified_source_hashes'],historical_gap_observations=value['historical_price_cache_gap_observations'])
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)/'output.json'
            with patch.object(reader.drift,'load_contract',return_value={}),patch.object(reader,'verify_gap_observations'),patch.object(reader.drift,'verify_expected_sources',side_effect=[good,ValueError('drift after publication')]):
                with self.assertRaisesRegex(ValueError,'drift after publication'):
                    reader.publish_verified(output,value)
                self.assertTrue(output.is_file())

    def test_mismatched_partition_rejected_before_publication(self):
        required=dict(reader.LOADED,**{str(reader.AUDIT):reader.AUDIT_SHA})
        value=dict(schema='ndx_corrected_delta_paired_overlay_limited_drift_v2',
            historical_full_source_closure_verified=False,historical_expected_source_hashes=required,
            verified_source_hashes=dict(required,**{'false-old-gap':'sha'}),historical_price_cache_gap_observations=[])
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)/'output.json'
            with patch.object(reader.drift,'load_contract',return_value={}),patch.object(reader.drift,'verify_expected_sources',return_value=dict(verified_source_hashes={},historical_gap_observations=[])):
                with self.assertRaisesRegex(ValueError,'partition'):
                    reader.publish_verified(output,value)
            self.assertFalse(output.exists())

    def test_removed_loaded_source_is_rejected(self):
        value=dict(schema='ndx_corrected_delta_paired_overlay_limited_drift_v2',
            historical_full_source_closure_verified=False,historical_expected_source_hashes={},verified_source_hashes={})
        with tempfile.TemporaryDirectory() as directory,patch.object(reader.drift,'load_contract',return_value={}):
            output=Path(directory)/'output.json'
            with self.assertRaisesRegex(ValueError,'retain loaded sources'):
                reader.publish_verified(output,value)
            self.assertFalse(output.exists())


if __name__=='__main__':unittest.main()
