from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from backtest import ndx_corrected_delta_paired_overlay_research as pure
from scripts import ndx_corrected_delta_paired_overlay_research as reader


def fixture(schema='ndx_corrected_cohort_overlay_v1'):
    task=dict(job_id='paired',tickers='AAA;BBB',holding_count=2,weight_spec='constrained_fixed_shrinkage')
    pending=dict(task=task,origin='DELTA',status='PENDING_NUMERICAL_DELTA',result=None,overlay_mode='PENDING',lineage={},eligibility=None)
    base=dict(task=dict(task,job_id='base-pending'),origin='NON_EQUAL_BASE',status='PENDING_NUMERICAL_DELTA',result=None,lineage={})
    selected=dict(pending,task=dict(task,job_id='delta-selected'))
    available=dict(task=dict(task,job_id='equal'),origin='EQUAL_WEIGHT_BASE',status='AVAILABLE',result={'unchanged':True},lineage={})
    parent=dict(schema=schema,records=[pending,base,selected,available],original_count=4,available_count=1,pending_count=3,
        promotion_allowed=False,selection_performed=False,coordinate=dict(selection_date='2023-04-03'))
    old=dict(tickers=task['tickers'],holding_count=2,weight_spec=task['weight_spec'],**{key:.1 for key in pure.PAIRED_KEYS},
        return_p50=.2,return_p50_vs_012922=.01,whole_lot_path_return_net=.19,risk_chain_top1_max=.4)
    new=dict(old,paired_return_p50_vs_incumbent=.07)
    replacement=dict(task=task,original_result=old,result=new,lineage=dict(checkpoint_sha256='external'),
        historical_loader_provenance_gaps=[dict(path='historical.yaml',expected_historical_sha256='old',observed_current_sha256='new',
            original_pointer_preserved=True,used_as_current_numerical_input=False,status='HISTORICAL_SOURCE_DRIFT')],
        original_historical_provenance_verified=False,point_in_time_verified=False,promotion_allowed=False,
        reconstruction_scope='NUMERICAL_RECONSTRUCTION_WITH_HISTORICAL_LOADER_PROVENANCE_GAP')
    return parent,replacement


class DeltaOverlayTests(unittest.TestCase):
    def test_complete_paired_subqueue_merges_with_base_and_selected_still_pending(self):
        for schema in ('ndx_corrected_cohort_overlay_v1','ndx_corrected_base_overlay_v2'):
            parent,row=fixture(schema);before=deepcopy(parent)
            value=pure.extend_delta_paired_overlay(parent=parent,replacements=[row],expected_tasks=[row['task']])
            self.assertEqual(parent,before);self.assertEqual(value['records'][1:],parent['records'][1:])
            self.assertEqual((value['available_count'],value['pending_count'],value['delta_paired_added']),(2,2,1))
            self.assertFalse(value['input_artifact_binding_verified']);self.assertFalse(value['economic_inputs_complete'])
            self.assertFalse(value['original_historical_provenance_verified']);self.assertIsNone(value['winner'])

    def test_candidate_target_risk_wholelot_and_provenance_changes_rejected(self):
        for fault in ('return_p50','return_p50_vs_012922','risk_chain_top1_max','whole_lot_path_return_net','provenance','nan'):
            parent,row=fixture()
            if fault=='provenance':row['original_historical_provenance_verified']=True
            elif fault=='nan':row['result']['paired_return_p50_vs_incumbent']=float('nan')
            else:row['result'][fault]+=.001
            with self.assertRaises(ValueError,msg=fault):pure.extend_delta_paired_overlay(parent=parent,replacements=[row],expected_tasks=[row['task']])

    def test_missing_duplicate_unknown_and_already_available_rejected(self):
        parent,row=fixture()
        for replacements in ([],[row,row],[dict(row,task=dict(row['task'],job_id='unknown'))]):
            with self.assertRaises(ValueError):pure.extend_delta_paired_overlay(parent=parent,replacements=replacements,expected_tasks=[row['task']])
        parent['records'][0]['status']='AVAILABLE'
        with self.assertRaises(ValueError):pure.extend_delta_paired_overlay(parent=parent,replacements=[row],expected_tasks=[row['task']])

    def test_reader_refuses_incomplete_whole614_index_before_task_readback(self):
        with tempfile.TemporaryDirectory() as directory:
            paths=[]
            for name,value in [('parent',{}),('index',dict(schema='ndx_delta_paired_snapshot_completion_index_v1',status='PARTIAL')),('audit',{})]:
                path=Path(directory)/(name+'.json');raw=json.dumps(value).encode();path.write_bytes(raw);paths.extend([path,hashlib.sha256(raw).hexdigest()])
            # Only the immutable hard plan read is replaced; no evaluator is involved.
            def read_bytes(path):
                return b'{}' if path==reader.PLAN else original(path)
            original=Path.read_bytes
            with patch.object(reader,'PLAN_SHA',hashlib.sha256(b'{}').hexdigest()),patch.object(Path,'read_bytes',read_bytes):
                with self.assertRaisesRegex(ValueError,'Entire 614'):
                    reader.build(parent_path=paths[0],parent_sha256=paths[1],index_path=paths[2],index_sha256=paths[3],audit_path=paths[4],audit_sha256=paths[5])

    def test_publication_source_drift_never_returns_success(self):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'source';source.write_bytes(b'original');output=Path(directory)/'overlay.json'
            value=dict(source_hashes={str(source):hashlib.sha256(source.read_bytes()).hexdigest()});publish=reader.publish
            def changed(path,data):
                result=publish(path,data);source.write_bytes(b'changed during publish');return result
            with patch.object(reader,'publish',side_effect=changed):
                with self.assertRaisesRegex(ValueError,'publication'):reader.publish_verified(output,value)

    def test_actual_gap_file_drift_during_publication_is_rejected_without_resigning_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'historical.yaml';path.write_bytes(b'observed version')
            gap=dict(path=str(path),expected_historical_sha256=reader.GAP_EXPECTED_SHA,
                observed_current_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),status='HISTORICAL_SOURCE_DRIFT',
                original_pointer_preserved=True,used_as_current_numerical_input=False)
            value=dict(source_hashes={},historical_loader_gap_observations=[gap]);original=deepcopy(value);publish=reader.publish
            def changed(output,data):
                result=publish(output,data);path.write_bytes(b'changed during output write');return result
            with patch.object(reader,'GAP_PATH',str(path)),patch.object(reader,'publish',side_effect=changed):
                with self.assertRaisesRegex(ValueError,'gap observation drifted'):
                    reader.publish_verified(Path(directory)/'overlay.json',value)
            self.assertEqual(value,original);self.assertNotIn(str(path),value['source_hashes'])

    def test_gap_none_requires_absence_and_exact_historical_pointer(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'historical.yaml'
            gap=dict(path=str(path),expected_historical_sha256=reader.GAP_EXPECTED_SHA,observed_current_sha256=None,
                status='UNAVAILABLE',original_pointer_preserved=True,used_as_current_numerical_input=False)
            with patch.object(reader,'GAP_PATH',str(path)):
                reader.verify_gap_observations([gap])
                with self.assertRaises(ValueError):reader.verify_gap_observations([dict(gap,expected_historical_sha256='0'*64)])
                path.mkdir()
                with self.assertRaisesRegex(ValueError,'not a regular file'):reader.verify_gap_observations([gap])
