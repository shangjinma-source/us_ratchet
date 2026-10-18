"""Synthetic CPRT values with saved parent metadata; no actual channel recomputation."""
from copy import deepcopy
from decimal import Decimal, Context, localcontext, Inexact
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_new_cutoff_typed_panel_v3_independent_readback_20260925 as module


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
            self.assertEqual(calculate.call_args.args[0]['ticker'],'CPRT')
            return result

    def test_increment_counts_old_frames_and_crwd_block(self):
        candidate=self.candidate();decoded=self.verify(candidate)
        self.assertEqual((decoded['conditional_security_count'],decoded['conditional_issuer_count']),(21,20))
        self.assertNotIn('CRWD',decoded['returns'].columns)
        gap=module.one(decoded['observed_provenance_and_missing'],'CRWD')
        self.assertEqual(gap['blocking_reasons'],['BLOCKED_VOLUME_UNIT_UNKNOWN'])
        self.assertEqual(gap['coordinate_assumption']['dated_fact']['dated_as_of'],'2026-06-09')
        self.assertEqual(candidate['original_evidence_and_projection'],self.documents['parent_panel']['original_evidence_and_projection'])

    def test_rechecksummed_old_cell_and_false_candidate_count_rejected(self):
        for attack in ('old_cell','count','authority'):
            candidate=self.candidate();panel=module.codec.decode_frames(candidate['panel'])
            if attack=='old_cell':panel['returns'].iloc[0,0]+=.01
            elif attack=='count':panel['conditional_security_count']=22
            else:panel['point_in_time_verified']=True
            panel['panel_content_sha256']=module.codec.checksum(panel);candidate['panel']=module.codec.encode_frames(panel)
            with self.subTest(attack=attack),self.assertRaises(ValueError):self.verify(candidate)

    def test_sidecar_loss_and_forged_exact_proof_rejected(self):
        for attack in ('sidecar','proof','late'):
            candidate=self.candidate()
            if attack=='sidecar':candidate['original_evidence_and_projection'].pop()
            elif attack=='proof':candidate['original20_frame_exact_proof']['returns']['original_sha256']='0'*64
            else:candidate['v3_incremental_evidence_and_projection'][0]['early_window_review_availability_verified']=True
            with self.subTest(attack=attack),self.assertRaises(ValueError):self.verify(candidate)

    def test_parent_audit_boolean_reconstruction_rejected(self):
        documents=deepcopy(self.documents);documents['parent_readback']['increment_reconstruction_count']=True
        with patch.object(module.codec,'channel_numbers') as numbers,self.assertRaises(ValueError):module.reconstruct_increment(documents)
        numbers.assert_not_called()

    def test_independent_numeric_fraction_and_float_decimal_order(self):
        days=self.documents['channels']['calendar'];price=10.000000000000002;volume=10000001
        with localcontext(Context(prec=50)):
            dollar=Decimal(str(price))*volume
            value=float(Decimal(str(price))*Decimal(2)/Decimal(3)/Decimal(str(price))-1)
        channel=dict(schema='CONDITIONAL_PROVIDER_CHANNEL_INPUT_V1',ticker='CPRT',calendar=days,cutoff=days[-1],price_rows=[dict(session=d,nominal_close=price) for d in days],price_returns=[dict(previous_session=a,session=b,price_return=value,declared_share_ratio='2/3') for a,b in zip(days,days[1:])],liquidity=dict(status='CONDITIONAL_RAW_VOLUME_TIMES_NOMINAL_CLOSE',rows=[dict(session=d,raw_volume=volume,dollar_volume=str(dollar)) for d in days[-63:]],median_dollar_volume_usd=str(dollar),numerical_threshold_passed=True),minimum_median_dollar_volume_usd=50000000,**dict.fromkeys(module.codec.CHANNEL_FALSE,False))
        with localcontext() as context:
            context.prec=2;context.traps[Inexact]=True
            numbers=module.codec.channel_numbers(channel,days)
        self.assertEqual(numbers[0],[value]*126);self.assertEqual(numbers[2]['dollars'],[float(dollar)]*63)
        self.assertEqual(numbers[2]['volumes'],[volume]*63)
    def test_full_parent_sidecars_and_late_review_preserved(self):
        candidate=self.candidate()
        self.assertEqual(candidate['incremental_evidence_and_projection'],self.documents['parent_panel']['incremental_evidence_and_projection'])
        saved=candidate['v3_incremental_evidence_and_projection'][0]
        self.assertEqual(saved['saved_review_selection_date'],'2026-07-13');self.assertFalse(saved['early_window_review_availability_verified'])
        self.assertIsNone(saved['complete_extended_provenance']['complete_increment_evidence']['original_business_fact']['assigned_risk_chain'])
        changed=deepcopy(candidate);changed['incremental_evidence_and_projection'][0]['original_gap']={}
        with self.assertRaises(ValueError):self.verify(changed)

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
