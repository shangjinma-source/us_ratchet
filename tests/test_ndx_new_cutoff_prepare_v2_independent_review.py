"""Saved metadata decoding only; no planner or audit invocation."""
from copy import deepcopy
import unittest
from unittest.mock import patch
import test_ndx_new_cutoff_shard_prepare_v2_20260924 as fixture
m=fixture.module

class IndependentPrepareV2Review(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixture.Tests.setUpClass();cls.docs=fixture.Tests.documents;cls.sources=fixture.Tests.sources

    def test_increment_column_claims_and_inner_schema_cannot_be_downgraded(self):
        for attack in ('crwd','pcar','inner'):
            docs=deepcopy(self.docs)
            if attack=='crwd':docs['panel']['incremental_evidence_and_projection'][1]['numerical_column_added']=True
            elif attack=='pcar':docs['panel']['incremental_evidence_and_projection'][0]['numerical_column_added']=False
            else:
                decoded=m.reader.decode_frames(docs['panel']['panel']);decoded['schema']='LATEST_CONDITIONAL_TYPED_PANEL_V1'
                decoded['panel_content_sha256']=m.reader.checksum(decoded);docs['panel']['panel']=m.reader.encode_frames(decoded)
            with self.subTest(attack=attack),self.assertRaises(ValueError):m.inputs_from_documents(docs,self.sources)

    def test_actual_groups_keep_pcar_and_google_classes_exclude_crwd(self):
        with patch.object(m.planning,'prepare_issuer_shards',side_effect=AssertionError('real prepare')):
            groups,params,decoded=m.inputs_from_documents(self.docs,self.sources)
        self.assertEqual(len(groups),19);self.assertEqual(sum(len(s) for _,s in groups),20)
        self.assertEqual(dict(groups)['issuer:0000075362'],['security:0000075362:693718108'])
        self.assertEqual(len(dict(groups)['issuer:0001652044']),2)
        self.assertNotIn('issuer:0001535527',dict(groups));self.assertEqual(params,m.PARAMETERS)

    def test_source_pin_override_and_consumed_blob_attack_fail_before_prepare(self):
        for path in (str(m.V2_READER),str(m.V2_PRODUCER)):
            with self.assertRaises(ValueError):m.guard({path:'0'*64})
        with patch.object(m,'guard'),patch.object(m.Path,'read_bytes',return_value=b'wrong'),patch.object(m.planning,'prepare_issuer_shards') as prepare:
            with self.assertRaises(ValueError):m.build()
            prepare.assert_not_called()

if __name__=='__main__':unittest.main()
