"""Bound metadata validation only; never build a real interval plan or fit."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_new_cutoff_shard_prepare_v3_20260925 as module


class Tests(unittest.TestCase):
    def test_closed_form_count_guard_and_capacity_without_prepare(self):
        self.assertEqual((module.SHARD_SIZE,module.MAX_SHARDS),(1000,2000))
        result=dict(all_k_combination_count=1572863,necessary_bound_excluded_combination_count=1541,planned_combination_count=1571322,
            planned_canonical_task_count=4713966,planned_shard_count=1581,completed_canonical_task_count=0,remaining_canonical_task_count=4713966,
            cardinalities=[dict(k=k,necessary_bound_certificates=['synthetic'] if k<=3 else []) for k in range(1,21)])
        module.validate_counts(result)
        for key,value in [('completed_canonical_task_count',False),('planned_shard_count',1000),('remaining_canonical_task_count',4713870)]:
            bad=deepcopy(result);bad[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):module.validate_counts(bad)

    def test_third_sidecar_and_external_index_not_optional(self):
        for attack in ('cprt','completed'):
            docs=deepcopy(self.documents)
            if attack=='cprt':docs['panel']['v3_incremental_evidence_and_projection']=[]
            else:docs['completed_index']['batch_saved_attempt_count']=True
            with self.subTest(attack=attack),self.assertRaises(ValueError):module.inputs_from_documents(docs,self.sources)

    @classmethod
    def setUpClass(cls):
        cls.documents={}
        for role in module.BOUND:
            raw=Path(module.reference(role)['path']).read_bytes()
            cls.documents[role]=module.yaml.safe_load(raw) if role=='search' else module.reader.loads(raw)
        cls.sources=module.fitter._sources()

    def test_complete_grouping_and_preserved_parameters_without_execution(self):
        with patch.object(module.planning,'prepare_issuer_shards') as prepare, patch.object(module.reader,'build') as audit:
            groups,parameters,panel=module.inputs_from_documents(self.documents,self.sources)
            self.assertEqual((len(groups),sum(len(sids) for issuer,sids in groups)),(20,21))
            self.assertEqual(sorted(len(sids) for issuer,sids in groups),[1]*19+[2])
            self.assertEqual(parameters,module.PARAMETERS)
            self.assertEqual(panel['cutoff'],'2026-09-21')
            prepare.assert_not_called();audit.assert_not_called()

    def test_audit_parent_scope_and_boolean_counter_attacks(self):
        mutations=[('increment_reconstruction_count',True),('typed_roundtrip_exact',False),
                   ('full_original101_and_incremental_sidecars_compared',False),('fit_performed',True),
                   ('point_in_time_verified',True),('candidate_reference',{'path':'wrong','sha256':'0'*64})]
        for key,value in mutations:
            documents=deepcopy(self.documents);documents['audit'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):
                module.inputs_from_documents(documents,self.sources)

    def test_audit_shapes_and_denominator_required(self):
        for key,value in [('observed_security_count',100),('conditional_security_count',18),('frame_shapes',{})]:
            documents=deepcopy(self.documents);documents['audit'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):
                module.inputs_from_documents(documents,self.sources)

    def test_parameters_and_numerical_closure_cannot_drift(self):
        documents=deepcopy(self.documents);documents['search']['search_contract']['max_single_weight']=.5
        with self.assertRaises(ValueError):module.inputs_from_documents(documents,self.sources)
        sources=dict(self.sources);sources.pop(next(iter(sources)))
        with self.assertRaises(ValueError):module.inputs_from_documents(self.documents,sources)
        sources=dict(self.sources);sources[next(iter(sources))]='0'*64
        with self.assertRaises(ValueError):module.inputs_from_documents(self.documents,sources)

    def test_prior_cutoff_is_metadata_only_and_required(self):
        documents=deepcopy(self.documents);documents['old_plan_metadata']['cutoff']='2026-09-21'
        with self.assertRaises(ValueError):module.inputs_from_documents(documents,self.sources)

    def test_v2_increment_provenance_cannot_be_replaced_by_v1(self):
        for key,value in [('original_twenty_five_frames_exact',False),('unchanged_other100_gaps_exact',False),
            ('independently_recomputed_tickers',['PCAR','CRWD']),('schema','NEW_CUTOFF_TYPED_PANEL_INDEPENDENT_READBACK_V1')]:
            documents=deepcopy(self.documents);documents['audit'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):module.inputs_from_documents(documents,self.sources)
        documents=deepcopy(self.documents);documents['audit']['source_hashes'][str(module.V3_READER)]='0'*64
        with self.assertRaises(ValueError):module.inputs_from_documents(documents,self.sources)
        documents=deepcopy(self.documents);documents['panel']['incremental_evidence_and_projection'].pop()
        with self.assertRaises(ValueError):module.inputs_from_documents(documents,self.sources)

    def test_loaded_source_conflict_not_silently_overwritten(self):
        with self.assertRaises(ValueError):module.guard({str(module.SOURCE):'0'*64})

    def test_completed_namespace_rejected_before_build_and_source_drift(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(module,'OUTPUT',Path(directory)/'plan.json'),patch.object(module,'build') as build:
            with self.assertRaises(ValueError):module.publish()
            build.assert_not_called()
        with patch.object(module.Path,'read_bytes',return_value=b'drift'):
            with self.assertRaises(ValueError):module.guard({})


if __name__=='__main__':unittest.main()
