"""Synthetic closed-form and fail-closed tests; never invoke the actual planner."""
from copy import deepcopy
from math import comb,ceil
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_new_cutoff_shard_prepare_v6_20260925 as m


def synthetic_counts():
    counts={k:(comb(22,k) if k<=22 else 0)+2*comb(22,k-1) for k in range(1,24)}
    excluded={1,2,3,21,22,23}
    planned=sum(v for k,v in counts.items() if k not in excluded)
    return dict(all_k_combination_count=sum(counts.values()),necessary_bound_excluded_combination_count=sum(counts[k] for k in excluded),
        planned_combination_count=planned,planned_canonical_task_count=3*planned,
        planned_shard_count=sum(ceil(v/1000) for k,v in counts.items() if k not in excluded),
        completed_canonical_task_count=0,remaining_canonical_task_count=3*planned,
        cardinalities=[dict(k=k,combination_count=counts[k],planned_combination_count=0 if k in excluded else counts[k],
            planned_canonical_task_count=0 if k in excluded else 3*counts[k],planned_shard_count=0 if k in excluded else ceil(counts[k]/1000),
            necessary_bound_certificates=['synthetic necessary certificate'] if k in excluded else []) for k in counts])


class Tests(unittest.TestCase):
    def test_available_metadata_anchors_exact(self):
        import hashlib
        for role,(path,digest) in m.BOUND.items():
            if digest is not None:
                self.assertEqual(hashlib.sha256((m.BASE/path).read_bytes()).hexdigest(),digest)
        self.assertEqual(m.BOUND['completed_index'][1],'274e194d7d00fd2cf5130476b9d82e1a9c6f4decc5a62ab6a9e3ff842b425db8')
    def test_independent_polynomial_denominators_and_capacity(self):
        coefficients=[1]
        for size in [2]+[1]*22:
            next_coefficients=[0]*(len(coefficients)+1)
            for k,count in enumerate(coefficients):
                next_coefficients[k]+=count;next_coefficients[k+1]+=size*count
            coefficients=next_coefficients
        value=synthetic_counts()
        self.assertEqual(coefficients[1:],[c['combination_count'] for c in value['cardinalities']])
        self.assertEqual(coefficients[-3:],[484,45,2])
        self.assertEqual(value['all_k_combination_count'],12582911)
        self.assertEqual(value['planned_canonical_task_count'],37740237)
        self.assertLess(8000,value['planned_shard_count']);self.assertGreaterEqual(m.MAX_SHARDS,value['planned_shard_count'])

    def test_closed_form_all_k_without_planner(self):
        with patch.object(m.planning,'prepare_issuer_shards') as prepare:
            value=synthetic_counts();m.validate_counts(value)
            self.assertEqual((m.SHARD_SIZE,m.MAX_SHARDS),(1000,16000))
            self.assertEqual(value['planned_shard_count'],12587)
            self.assertEqual(value['necessary_bound_excluded_combination_count'],2832)
            prepare.assert_not_called()
    def test_last_cardinality_certificate_cannot_disappear(self):
        for attack in ('drop','certificate','double','bool_k'):
            value=synthetic_counts()
            if attack=='drop':value['cardinalities'].pop()
            elif attack=='certificate':value['cardinalities'][-1]['necessary_bound_certificates']=[]
            elif attack=='double':value['necessary_bound_excluded_combination_count']+=2
            else:value['cardinalities'][0]['k']=True
            with self.subTest(attack=attack),self.assertRaises(ValueError):m.validate_counts(value)
    def test_no_automatic_completed_deduction_or_boolean(self):
        for key,value in [('completed_canonical_task_count',False),('remaining_canonical_task_count',37740237-402),('planned_shard_count',True)]:
            doc=synthetic_counts();doc[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):m.validate_counts(doc)
    def test_missing_pin_before_read_or_planner(self):
        bound=deepcopy(m.BOUND);bound['audit']=(bound['audit'][0],None)
        with patch.object(m,'BOUND',bound),patch.object(m.Path,'read_bytes') as read,patch.object(m.planning,'prepare_issuer_shards') as prepare:
            with self.assertRaises(ValueError):m.build()
            read.assert_not_called();prepare.assert_not_called()
    def test_fixed_namespace_rejects_before_build(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(m,'OUTPUT',Path(directory)/'plan.json'),patch.object(m,'build') as build:
            with self.assertRaises(ValueError):m.publish()
            build.assert_not_called()


class MetadataTests(unittest.TestCase):
    def fixture(self):
        import test_ndx_v5_planner_data_review as saved_fixture
        docs,numerical,panel=saved_fixture.fixture()
        docs['panel']['schema']='NEW_CUTOFF_CONDITIONAL_TYPED_PANEL_DOCUMENT_V6'
        docs['panel']['v6_incremental_evidence_and_projection']=[dict(ticker='CTAS',numerical_column_added=True,early_window_review_availability_verified=False,early_window_local_evidence_available=False,publication_date='2024-08-21',publication_date_role='MEMORANDUM_PRINTED_DATE_NOT_LOCAL_AVAILABILITY',dated_anchor_role='MEMORANDUM_PRINTED_DATE_NOT_JOINT_AVAILABILITY')]
        audit=docs['audit'];audit.update(schema='NEW_CUTOFF_TYPED_PANEL_INCREMENT_INDEPENDENT_READBACK_V6',candidate_reference=m.reference('panel'),producer_reference=dict(path=str(m.V6_PRODUCER),sha256=m.V6_PRODUCER_SHA),source_hashes={str(m.V6_PRODUCER):m.V6_PRODUCER_SHA,str(m.V6_READER):m.V6_READER_SHA},original_twenty_three_five_frames_exact=True,independently_recomputed_tickers=['CTAS'],conditional_security_count=24,conditional_issuer_count=23)
        panel.update(schema='LATEST_CONDITIONAL_TYPED_PANEL_V6',conditional_security_count=24,conditional_issuer_count=23)
        panel['universe'].loc[len(panel['universe'])]=dict(security_id='S23',issuer_id='I22')
        audit['frame_shapes']={key:list(panel[key].shape) for key in m.reader.FRAMES}
        docs['completed_index'].update(schema='NEW_CUTOFF_ORLY_COMPLETED_TASK_INDEX_V1',batch_saved_attempt_and_readback_count=402)
        return docs,numerical,panel

    def test_full_six_layers_and_unknown_orly_publication(self):
        docs,numerical,panel=self.fixture()
        with patch.object(m.reader,'decode_frames',return_value=panel):
            groups,params,_=m.inputs_from_documents(docs,numerical)
            self.assertEqual((len(groups),sum(len(s) for _,s in groups)),(23,24))
            for attack in ('ctas','orly','oldcount','crwd'):
                bad=deepcopy(docs)
                if attack=='ctas':bad['panel']['v6_incremental_evidence_and_projection'][0]['publication_date_role']='JOINT_AVAILABLE'
                elif attack=='orly':bad['panel']['v5_incremental_evidence_and_projection'][0]['publication_date']='2025-06-09'
                elif attack=='oldcount':bad['completed_index']['batch_saved_attempt_and_readback_count']=300
                else:bad['panel']['incremental_evidence_and_projection'][1]['numerical_column_added']=True
                with self.subTest(attack=attack),self.assertRaises(ValueError):m.inputs_from_documents(bad,numerical)


if __name__=='__main__':unittest.main()
