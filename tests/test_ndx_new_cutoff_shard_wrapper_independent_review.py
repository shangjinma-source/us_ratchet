"""Saved metadata/typed decode only; never actual build, planner or fit."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import yaml
from scripts import ndx_new_cutoff_shard_prepare_20260924 as m


class IndependentPrepareWrapperReview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.docs={role:(yaml.safe_load((m.BASE/path).read_bytes()) if role=='search' else json.loads((m.BASE/path).read_bytes())) for role,(path,_) in m.BOUND.items()}
        cls.numerical=m.fitter._sources()  # source-byte metadata only, no refit

    def test_saved_decode_retains_classes_without_audit_or_planner_calls(self):
        with patch.object(m.reader,'build',side_effect=AssertionError('repeat audit')),patch.object(m.planning,'prepare_issuer_shards',side_effect=AssertionError('real prepare')),patch.object(m.fitter,'refit_dynamic_cutoff_weights',side_effect=AssertionError('fit')):
            groups,params,decoded=m.inputs_from_documents(self.docs,self.numerical)
        self.assertEqual(len(groups),18);self.assertEqual(sum(len(s) for _,s in groups),19)
        google=dict(groups)['issuer:0001652044']
        self.assertEqual(set(google),{'security:0001652044:02079K107','security:0001652044:02079K305'})
        self.assertEqual(params,m.PARAMETERS);self.assertEqual(len(decoded['observed_provenance_and_missing']),101)

    def test_numerical_closure_missing_extra_or_hash_change_rejected(self):
        for attack in ('missing','extra','hash'):
            sources=deepcopy(self.numerical);key=next(iter(sources))
            if attack=='missing':sources.pop(key)
            elif attack=='extra':sources[str(Path(__file__).resolve())]='a'*64
            else:sources[key]='0'*64
            with self.subTest(attack=attack),self.assertRaisesRegex(ValueError,'numerical closure'):
                m.inputs_from_documents(self.docs,sources)

    def test_saved_audit_and_parameter_claims_cannot_be_upgraded(self):
        for attack in ('count_bool','fit','parameter','oldcutoff','legal'):
            docs=deepcopy(self.docs)
            if attack=='count_bool':docs['audit']['reconstruction_count']=True
            elif attack=='fit':docs['audit']['fit_performed']=True
            elif attack=='parameter':docs['search']['search_contract']['turnover_anchor_strength']=.26
            elif attack=='oldcutoff':docs['old_plan_metadata']['cutoff']='2026-09-21'
            else:docs['panel']['legal_training_input_admitted']=True
            with self.subTest(attack=attack),self.assertRaises(ValueError):m.inputs_from_documents(docs,self.numerical)

    def test_existing_namespace_and_consumed_bytes_stop_before_planner(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(m,'OUTPUT',Path(folder)/'plan.json'),patch.object(m,'build') as build:
            with self.assertRaises(ValueError):m.publish()
            build.assert_not_called()
        with patch.object(m,'guard'),patch.object(m.Path,'read_bytes',return_value=b'changed'),patch.object(m.planning,'prepare_issuer_shards') as prepare:
            with self.assertRaisesRegex(ValueError,'Consumed source bytes'):m.build()
            prepare.assert_not_called()


if __name__=='__main__':unittest.main()
