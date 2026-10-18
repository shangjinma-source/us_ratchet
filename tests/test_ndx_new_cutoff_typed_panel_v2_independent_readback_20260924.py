"""Synthetic PCAR values with saved parent metadata; no actual channel recomputation."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_new_cutoff_typed_panel_v2_independent_readback_20260924 as module


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.documents={role:module.codec.loads(Path(module.ref(role)['path']).read_bytes()) for role in module.BOUND}
        cls.numbers=([0.01]*126,[200.0]*127,dict(volumes=[500000]*63,dollars=[100000000.0]*63,median=100000000.0),None)

    def candidate(self):
        with patch.object(module.codec,'channel_numbers',return_value=self.numbers):
            value=module.reconstruct_increment(self.documents)
        value['source_hashes']={};return value

    def verify(self,candidate):
        with patch.object(module.codec,'channel_numbers',return_value=self.numbers) as calculate,patch.object(module.codec,'build',side_effect=AssertionError('old audit')):
            result=module.verify_candidate(candidate,self.documents,{})
            self.assertEqual(calculate.call_count,1)
            self.assertEqual(calculate.call_args.args[0]['ticker'],'PCAR')
            return result

    def test_increment_counts_old_frames_and_crwd_block(self):
        candidate=self.candidate();decoded=self.verify(candidate)
        self.assertEqual((decoded['conditional_security_count'],decoded['conditional_issuer_count']),(20,19))
        self.assertNotIn('CRWD',decoded['returns'].columns)
        gap=module.one(decoded['observed_provenance_and_missing'],'CRWD')
        self.assertEqual(gap['blocking_reasons'],['BLOCKED_VOLUME_UNIT_UNKNOWN'])
        self.assertEqual(gap['coordinate_assumption']['dated_fact']['dated_as_of'],'2026-06-09')
        self.assertEqual(candidate['original_evidence_and_projection'],self.documents['parent_panel']['original_evidence_and_projection'])

    def test_rechecksummed_old_cell_and_false_candidate_count_rejected(self):
        for attack in ('old_cell','count','authority'):
            candidate=self.candidate();panel=module.codec.decode_frames(candidate['panel'])
            if attack=='old_cell':panel['returns'].iloc[0,0]+=.01
            elif attack=='count':panel['conditional_security_count']=21
            else:panel['point_in_time_verified']=True
            panel['panel_content_sha256']=module.codec.checksum(panel);candidate['panel']=module.codec.encode_frames(panel)
            with self.subTest(attack=attack),self.assertRaises(ValueError):self.verify(candidate)

    def test_sidecar_loss_and_forged_exact_proof_rejected(self):
        for attack in ('sidecar','proof','late'):
            candidate=self.candidate()
            if attack=='sidecar':candidate['original_evidence_and_projection'].pop()
            elif attack=='proof':candidate['original19_frame_exact_proof']['returns']['original_sha256']='0'*64
            else:candidate['incremental_evidence_and_projection'][1]['early_window_evidence_available']=True
            with self.subTest(attack=attack),self.assertRaises(ValueError):self.verify(candidate)

    def test_parent_audit_boolean_reconstruction_rejected(self):
        documents=deepcopy(self.documents);documents['parent_readback']['reconstruction_count']=True
        with patch.object(module.codec,'channel_numbers') as numbers,self.assertRaises(ValueError):module.reconstruct_increment(documents)
        numbers.assert_not_called()

    def test_source_map_drift_and_existing_audit_no_rebuild(self):
        candidate=self.candidate();candidate['source_hashes']={'fake':'0'*64}
        with self.assertRaises(ValueError):self.verify(candidate)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'audit.json';path.write_text('{}')
            with patch.object(module,'OUTPUT',path),patch.object(module,'build') as build:
                with self.assertRaises(ValueError):module.publish()
                build.assert_not_called()
        with patch.object(module.Path,'read_bytes',return_value=b'drift'):
            with self.assertRaises(ValueError):module.guard({})


if __name__=='__main__':unittest.main()
