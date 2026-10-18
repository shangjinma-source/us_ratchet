"""Metadata adapter tests with an explicitly incomplete plan stub; no actual slice."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_new_cutoff_bounded_materialize_20260924 as module


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.documents={role:module.codec.loads(Path(module.ref(role)['path']).read_bytes())
            for role in module.BOUND if role!='plan'}
        cls.numerical=module.fitter._sources()
        panel=cls.documents['panel']['panel'];audit=cls.documents['audit']
        # This stub validates the outer metadata adapter only, never the pure plan contract.
        plan=dict(context=dict(panel_reference=module.ref('panel'),panel_audit_reference=module.ref('audit'),
            decision_cutoff='2026-09-21',previous_target_weights=None,
            parameters=deepcopy(cls.documents['old_plan_metadata']['canonical_tasks'][0]['parameters'])),
            fitter_source_hashes=deepcopy(cls.numerical),cardinalities=[dict(k=k,necessary_bound_certificates=['stub'] if k<4 else []) for k in range(1,5)],
            shards=[dict(k=4,start=0,shard_id='a'*64)])
        cls.documents['plan']=dict(schema='SOURCE_BOUND_NEW_CUTOFF_SHARD_PREPARE_V2',input_references=dict(panel=module.ref('panel'),audit=module.ref('audit')),
            plan=plan,conditional_security_count=20,conditional_issuer_count=19,panel_content_sha256=panel['panel_content_sha256'],
            **dict.fromkeys(('fit_performed','combination_enumeration_performed','task_inputs_materialized','execution_authorized',
                'point_in_time_verified','legal_training_input_admitted','promotion_allowed'),False))

    def test_projection_is_complete_and_does_not_materialize(self):
        with patch.object(module.materializer,'materialize_slice') as materialize,patch.object(module.codec,'build') as audit:
            result=module.inputs(self.documents,self.numerical)
            self.assertEqual((result['start'],result['stop'],result['max_materialized_combinations']),(0,1,1))
            self.assertEqual((len(result['panel']['dates']),len(result['panel']['columns']),len(result['panel']['universe'])),(126,20,20))
            self.assertNotIn('CRWD',result['panel']['columns']);self.assertIn('PCAR',result['panel']['columns'])
            materialize.assert_not_called();audit.assert_not_called()

    def test_parent_scope_count_and_increment_audit_attacks(self):
        for role,key,value in [('audit','increment_reconstruction_count',True),('audit','original_nineteen_five_frames_exact',False),
            ('plan','conditional_security_count',21),('plan','fit_performed',True),('panel','point_in_time_verified',True)]:
            documents=deepcopy(self.documents);documents[role][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):module.inputs(documents,self.numerical)

    def test_parent_reference_and_prior_rejected(self):
        for attack in ('parent','prior','first_shard'):
            documents=deepcopy(self.documents)
            if attack=='parent':documents['plan']['input_references']['panel']['sha256']='0'*64
            elif attack=='prior':documents['plan']['plan']['context']['previous_target_weights']={}
            else:documents['plan']['plan']['shards'][0]['start']=1
            with self.subTest(attack=attack),self.assertRaises(ValueError):module.inputs(documents,self.numerical)

    def test_numerical_source_and_original_parameters_rejected(self):
        numerical=dict(self.numerical);numerical.pop(next(iter(numerical)))
        with self.assertRaises(ValueError):module.inputs(self.documents,numerical)
        documents=deepcopy(self.documents);documents['plan']['plan']['context']['parameters']['top_weight_cap']=.9
        with self.assertRaises(ValueError):module.inputs(documents,self.numerical)

    def test_missing_fixed_plan_anchor_rejected_before_io(self):
        bound=deepcopy(module.BOUND);bound['plan']=(bound['plan'][0],None)
        with patch.object(module,'BOUND',bound),patch.object(module.materializer,'materialize_slice') as materialize:
            with self.assertRaises(ValueError):module.build()
            materialize.assert_not_called()

    def test_existing_namespace_rejects_before_build_and_guard_detects_drift(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(module,'OUTPUT',Path(directory)/'materialized.json'),patch.object(module,'build') as build:
            with self.assertRaises(ValueError):module.publish()
            build.assert_not_called()
        with patch.object(module.Path,'read_bytes',return_value=b'drift'):
            with self.assertRaises(ValueError):module.guard({})


if __name__=='__main__':unittest.main()
