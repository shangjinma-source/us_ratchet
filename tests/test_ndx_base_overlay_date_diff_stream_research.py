from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import weakref
from scripts import ndx_base_overlay_date_diff_stream_research as reader


def write(path,value):
    raw=json.dumps(value,sort_keys=True).encode();Path(path).write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def fixture(directory):
    directory=Path(directory)
    originals=[dict(task=dict(job_id='base'+str(i)),origin='NON_EQUAL_BASE',status='PENDING_NUMERICAL_DELTA',result=None,
        overlay_mode='PENDING',lineage=dict(original_checkpoint_sha256='original'+str(i)),eligibility=None) for i in range(2)]
    originals.append(dict(task=dict(job_id='equal'),origin='EQUAL_WEIGHT_BASE',status='AVAILABLE',result=dict(kept=1),lineage={}))
    originals.append(dict(task=dict(job_id='delta'),origin='DELTA',status='PENDING_NUMERICAL_DELTA',result=None,lineage={}))
    parent=dict(coordinate=dict(selection_date='2024-06-03'),records=originals,original_count=4,available_count=1,pending_count=3,source_hashes={})
    parent_path=directory/'parent.json';parent_sha=write(parent_path,parent)
    updated=deepcopy(originals);entries=[]
    for i in range(2):
        result=dict(paired_return_p50_vs_incumbent=.1+i,return_p50=.2+i)
        checkpoint=dict(kind='checkpoint',result=dict(cache_checkpoint_sha256='original'+str(i),evaluation=dict(result=result)))
        path=directory/('checkpoint'+str(i)+'.json');sha=write(path,checkpoint);entries.append(dict(path=str(path),sha256=sha))
        updated[i].update(result=result,status='AVAILABLE',overlay_mode='BASE_WINDOW_DELTA_COMPLETE_DATE')
        updated[i]['lineage']['completed_base_delta']=dict(checkpoint_path=str(path),checkpoint_sha256=sha)
    index=dict(kind='shared_index',status='COMPLETE',finalization=dict(status='COMPLETE'),completed=entries)
    index_path=directory/'index.json';index_sha=write(index_path,index)
    for row in updated[:2]:row['lineage']['completed_base_delta'].update(complete_index_path=str(index_path),complete_index_sha256=index_sha)
    new=dict(parent,records=updated,parent_overlay_path=str(parent_path),parent_overlay_sha256=parent_sha,available_count=3,pending_count=1,
        point_in_time_verified=False,promotion_allowed=False,selection_performed=False,whole_lot_executed=False,winner=None,economic_inputs_complete=False)
    return directory/'new.json',new


class StreamingDiffTests(unittest.TestCase):
    def test_shared_index_once_and_each_checkpoint_released_before_next(self):
        class Tracked(dict):pass
        with tempfile.TemporaryDirectory() as directory:
            path,new=fixture(directory);sha=write(path,new);original_loads=json.loads;references=[];index_reads=[]
            def track(raw):
                value=original_loads(raw)
                if value.get('kind')=='checkpoint':
                    self.assertTrue(all(reference() is None for reference in references))
                    value=Tracked(value);references.append(weakref.ref(value))
                elif value.get('kind')=='shared_index':index_reads.append(True)
                return value
            with patch.object(reader.json,'loads',side_effect=track):result=reader.audit(path,sha)
            self.assertEqual((result['replaced_base_pending'],result['other_records_exact']),(2,2))
            self.assertEqual(len(index_reads),1);self.assertEqual(len(references),2)
            self.assertTrue(all(reference() is None for reference in references))
            self.assertEqual(result['shared_index_cache_count'],1)

    def test_unrelated_field_and_missing_replacement_and_forged_paired_rejected(self):
        for fault in ('unrelated','missing','paired','inner_other'):
            with tempfile.TemporaryDirectory() as directory:
                path,new=fixture(directory)
                if fault=='unrelated':new['records'][2]['result']['kept']=2
                elif fault=='missing':new['records'][0]['status']='PENDING_NUMERICAL_DELTA';new['records'][0]['result']=None
                elif fault=='paired':new['records'][0]['result']['paired_return_p50_vs_incumbent']+=.05
                else:new['records'][0]['eligibility']=True
                with self.assertRaises(ValueError,msg=fault):reader.audit(path,write(path,new))

    def test_checkpoint_absent_from_external_index_rejected_even_if_result_matches(self):
        with tempfile.TemporaryDirectory() as directory:
            path,new=fixture(directory);lineage=new['records'][0]['lineage']['completed_base_delta'];index_path=Path(lineage['complete_index_path'])
            index=json.loads(index_path.read_bytes());index['completed'].pop(0);sha=write(index_path,index)
            for row in new['records'][:2]:row['lineage']['completed_base_delta']['complete_index_sha256']=sha
            with self.assertRaisesRegex(ValueError,'absent from completed external index'):reader.audit(path,write(path,new))
