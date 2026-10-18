"""Independent metadata counterexamples; no actual planner or fitter calls."""
from copy import deepcopy
import hashlib
import unittest
from unittest.mock import patch
import pandas as pd
from scripts import ndx_new_cutoff_shard_prepare_v5_20260925 as m


def fixture():
    numerical={str(m.Path(m.fitter.__file__).resolve()):m.FITTER_SHA,**{f'synthetic-source-{i}':'a'*64 for i in range(24)}}
    decoded={key:pd.DataFrame() for key in m.reader.FRAMES}
    decoded['universe']=pd.DataFrame([dict(security_id=f'S{i:02}',issuer_id=f'I{max(0,i-1):02}') for i in range(23)])
    decoded.update(schema='LATEST_CONDITIONAL_TYPED_PANEL_V5',cutoff='2026-09-21',panel_content_sha256='d'*64,
        observed_security_count=101,observed_issuer_count=100,conditional_security_count=23,conditional_issuer_count=22,
        observed_provenance_and_missing=[{} for _ in range(101)],**dict.fromkeys(m.reader.PANEL_FALSE,False))
    panel=dict(schema='NEW_CUTOFF_CONDITIONAL_TYPED_PANEL_DOCUMENT_V5',panel={},
        original_evidence_and_projection=[{} for _ in range(101)],
        incremental_evidence_and_projection=[dict(ticker='PCAR',numerical_column_added=True),dict(ticker='CRWD',numerical_column_added=False)],
        v3_incremental_evidence_and_projection=[dict(ticker='CPRT',numerical_column_added=True,early_window_review_availability_verified=False)],
        v4_incremental_evidence_and_projection=[dict(ticker='BKNG',numerical_column_added=True,early_window_review_availability_verified=False,early_window_local_evidence_available=False)],
        v5_incremental_evidence_and_projection=[dict(ticker='ORLY',numerical_column_added=True,early_window_review_availability_verified=False,early_window_local_evidence_available=False,
            publication_date=None,publication_date_verified=False,action_or_signature_date_used_as_publication=False,
            dated_anchor_role='VISUALLY_TRANSCRIBED_ORGANIZATIONAL_ACTION_DATE_NOT_PUBLICATION_OR_JOINT_AVAILABILITY')])
    flags=dict.fromkeys(('legal_training_input_admitted','point_in_time_verified','promotion_allowed','execution_authorized','full_transitive_source_closure_reverified'),False)
    panel.update(flags)
    audit=dict(schema='NEW_CUTOFF_TYPED_PANEL_INCREMENT_INDEPENDENT_READBACK_V5',status='PASSED',candidate_reference=m.reference('panel'),
        producer_reference=dict(path=str(m.V5_PRODUCER),sha256=m.V5_PRODUCER_SHA),full_original101_and_incremental_sidecars_compared=True,
        typed_roundtrip_exact=True,increment_reconstruction_count=1,original_twenty_two_five_frames_exact=True,unchanged_other100_gaps_exact=True,
        independently_recomputed_tickers=['ORLY'],source_hashes={str(m.V5_READER):m.V5_READER_SHA,str(m.V5_PRODUCER):m.V5_PRODUCER_SHA},
        panel_content_sha256=decoded['panel_content_sha256'],observed_security_count=101,conditional_security_count=23,conditional_issuer_count=22,
        frame_shapes={key:list(decoded[key].shape) for key in m.reader.FRAMES},producer_called=False,panel_core_called=False,old_raw_oracle_called=False,fit_performed=False,**flags)
    docs=dict(panel=panel,audit=audit,completed_index=dict(schema='NEW_CUTOFF_BKNG_COMPLETED_TASK_INDEX_V1',batch_saved_attempt_and_readback_count=300,all_plan_tasks_completed=False),
        old_plan_metadata=dict(schema='LATEST_CONDITIONAL_ALL_K_REFIT_PLAN_V1',cutoff='2026-09-17',canonical_tasks=[dict(parameters=deepcopy(m.PARAMETERS))],historical_expected_source_hashes=numerical.copy()),
        search=dict(search_contract=deepcopy(m.PARAMETERS)))
    return docs,numerical,decoded


class Tests(unittest.TestCase):
    def check(self,docs,numerical,decoded):
        with patch.object(m.reader,'decode_frames',return_value=decoded),patch.object(m.planning,'prepare_issuer_shards',side_effect=AssertionError('planner forbidden')):
            return m.inputs_from_documents(docs,numerical)
    def test_synthetic_metadata_positive_and_unknown_publication(self):
        docs,numerical,decoded=fixture();groups,params,_=self.check(docs,numerical,decoded)
        self.assertEqual((len(groups),sum(len(sids) for _,sids in groups)),(22,23))
        self.assertEqual(params,m.PARAMETERS)
        for field,value in [('publication_date','2025-06-09'),('publication_date_verified',True),('action_or_signature_date_used_as_publication',True),('dated_anchor_role','PUBLICATION')]:
            bad=deepcopy(docs);bad['panel']['v5_incremental_evidence_and_projection'][0][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):self.check(bad,numerical,decoded)
    def test_preserved_layers_and_no_completed_or_parameter_upgrade(self):
        docs,numerical,decoded=fixture()
        for attack in ('crwd','late','completed','sources','params'):
            bad=deepcopy(docs)
            if attack=='crwd':bad['panel']['incremental_evidence_and_projection'][1]['numerical_column_added']=True
            elif attack=='late':bad['panel']['v5_incremental_evidence_and_projection'][0]['early_window_local_evidence_available']=True
            elif attack=='completed':bad['completed_index']['batch_saved_attempt_and_readback_count']=198
            elif attack=='sources':bad['old_plan_metadata']['historical_expected_source_hashes']['synthetic-source-0']='b'*64
            else:bad['search']['search_contract']['min_single_weight']=.04
            with self.subTest(attack=attack),self.assertRaises(ValueError):self.check(bad,numerical,decoded)
    def test_polynomial_tail_and_full_denominator(self):
        coefficients=[1]
        for size in [2]+[1]*21:
            new=[0]*(len(coefficients)+1)
            for k,value in enumerate(coefficients):new[k]+=value;new[k+1]+=size*value
            coefficients=new
        excluded={1,2,3,21,22};planned=sum(v for k,v in enumerate(coefficients) if k and k not in excluded)
        value=dict(all_k_combination_count=sum(coefficients[1:]),necessary_bound_excluded_combination_count=sum(coefficients[k] for k in excluded),planned_combination_count=planned,
            planned_canonical_task_count=3*planned,planned_shard_count=sum((v+999)//1000 for k,v in enumerate(coefficients) if k and k not in excluded),completed_canonical_task_count=0,remaining_canonical_task_count=3*planned,
            cardinalities=[dict(k=k,combination_count=v,necessary_bound_certificates=['bound'] if k in excluded else [],planned_combination_count=0 if k in excluded else v,planned_canonical_task_count=0 if k in excluded else 3*v,planned_shard_count=0 if k in excluded else (v+999)//1000) for k,v in enumerate(coefficients) if k])
        m.validate_counts(value);self.assertEqual(coefficients[-2:],[43,2])
        for field,badvalue in [('combination_count',42),('planned_canonical_task_count',False)]:
            bad=deepcopy(value);bad['cardinalities'][-2][field]=badvalue
            with self.subTest(field=field),self.assertRaises(ValueError):m.validate_counts(bad)
    def test_final_all_direct_anchors_bytes(self):
        for path,digest in m.BOUND.values():self.assertEqual(hashlib.sha256((m.BASE/path).read_bytes()).hexdigest(),digest)
        for path,digest in ((m.V5_READER,m.V5_READER_SHA),(m.V5_PRODUCER,m.V5_PRODUCER_SHA)):
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),digest)

if __name__=='__main__':unittest.main()
