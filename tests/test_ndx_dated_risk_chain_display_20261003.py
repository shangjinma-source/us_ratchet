from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_dated_risk_chain_display_20261003 as m
from scripts import ndx_dated_path_risk_display_20261003 as producer_fixture
from backtest import ndx_dated_path_risk_display_research as projection
from backtest import ndx_saved_risk_chain_display_research as core
from test_ndx_dated_path_risk_display_wrapper_20261003 import summary_fixture
from test_ndx_dated_path_risk_display_research import fixture


def fixture_stream():
    summary=summary_fixture()
    for i,row in enumerate(summary['rows']):row['k']=4+i//96;row['weight_spec']=('equal','fixed','turnover')[i//32%3]
    ids=[r['numerical_task_id'] for r in summary['rows']]
    values={ids[0]:fixture(first=True),ids[1]:fixture(task_id=ids[1],missing=True)}
    lines=[];offset=0
    def emit(row):
        nonlocal offset
        line=m.enc(row)+b'\n';location=dict(record_index=len(lines),byte_start=offset,byte_stop=offset+len(line),row_sha256=m.sha(line));offset+=len(line);lines.append(line);return location
    index=producer_fixture.stream_paths(summary,dict.fromkeys(values,{}),lambda tid,refs:deepcopy(values[tid]),projection,emit)
    blob=b''.join(lines);shared=index.pop('shared_paths')
    index.update(schema='SOURCE_BOUND_DATED_PATH_RISK_DISPLAY_V1',task_jsonl_reference=dict(path='tasks.jsonl',sha256=m.sha(blob),byte_count=len(blob),record_count=2),shared_paths_reference={},source_hashes={},batch_failure_preserved={'reason':'synthetic partial'},unresolved_task_ids=[],undispatched_task_ids=ids[2:])
    return index,shared,blob


def parents_fixture(root):
    index,shared,blob=fixture_stream();parent=root/'parent';parent.mkdir()
    (parent/'started.json').write_bytes(b'{}');(parent/'tasks.jsonl').write_bytes(blob)
    sd=dict(schema='DATED_PATH_RISK_SHARED_PATHS_V1',shared_paths=shared)
    sr=m.save(parent/'shared_paths.json',sd);index['shared_paths_reference']=sr;index['task_jsonl_reference']['path']=str(parent/'tasks.jsonl')
    refs={}
    for role in ('producer','reader','projection_core'):
        path=root/(role+'.py');path.write_bytes(b'# synthetic identity only');refs[role]=m.ref(path,m.sha(path.read_bytes()))
    cp=Path(core.__file__);refs['core']=m.ref(cp,m.sha(cp.read_bytes()))
    index['source_hashes']={refs[k]['path']:refs[k]['sha256'] for k in ('producer','projection_core')}
    refs['index']=m.save(parent/'index.json',index)
    pub=dict(schema='DATED_PATH_RISK_DISPLAY_PUBLICATION_V1',status='PUBLISHED_SAVED_PATH_DISPLAY_ONLY',index_reference=refs['index'],source_hashes=index['source_hashes'],task_jsonl_reference=index['task_jsonl_reference'],shared_paths_reference=sr,**{k:v for k,v in producer_fixture.FLAGS.items()})
    refs['publication']=m.save(parent/'publication.json',pub)
    audit=dict(schema='DATED_PATH_RISK_DISPLAY_INDEPENDENT_READBACK_V1',status='PASS',index_reference=refs['index'],publication_reference=refs['publication'],reader_sha256=refs['reader']['sha256'],source_hashes={r['path']:r['sha256'] for r in refs.values()},planned_task_count=1632,projected_task_count=2,not_supplied_task_count=1630,verified_jsonl_sha256=m.sha(blob),verified_jsonl_bytes=len(blob),**dict.fromkeys(('producer_called','projection_core_called','economics_recomputed','risk_recomputed','formal_comparison_passed','point_in_time_verified','promotion_allowed'),False))
    refs['audit']=m.save(root/'audit.json',audit)
    return parent,{k:(r['path'],r['sha256']) for k,r in refs.items()}


class Tests(unittest.TestCase):
    def test_full_index_missing_and_shared_control_once(self):
        index,shared,blob=fixture_stream();before=deepcopy((index,shared));rows=[]
        out=m.project_stream(io.BytesIO(blob),index,shared,core,lambda row:rows.append(row) or dict(record_index=len(rows)-1))
        self.assertEqual((index,shared),before);self.assertEqual(out['planned_task_count'],1632)
        self.assertEqual(out['projected_task_count'],2);self.assertEqual(out['not_supplied_task_count'],1630)
        self.assertEqual(len(out['k_spec_coverage']),51);self.assertEqual(len(out['shared_control_aggregates']),2)
        self.assertIsNone(rows[1]['tracks']['candidate_integer']['rows'])
        self.assertEqual(len(rows[0]['tracks']['candidate_integer']['rows']),127)
        self.assertEqual(rows[0]['preserved_evidence_sidecars'],{'all7':'preserved'})
        self.assertIn('shared_aggregate_id',rows[0]['tracks']['incumbent_integer'])

    def test_input_order_shared_identity_and_complete_bytes(self):
        index,shared,blob=fixture_stream()
        for mode in ('booloffset','wrongtask','extraline','shared'):
            ix=deepcopy(index);sh=deepcopy(shared);b=blob
            if mode=='booloffset':ix['task_index'][0]['jsonl_record']['byte_start']=False
            elif mode=='wrongtask':ix['task_index'][0]['numerical_task_id']='f'*64
            elif mode=='extraline':b+=b'{}\n'
            else:next(iter(sh.values()))['identity']['role']='another'
            with self.subTest(mode=mode),self.assertRaises(ValueError):m.project_stream(io.BytesIO(b),ix,sh,core,lambda row:None)

    def test_success_and_late_output_drift_no_retry(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);parent,bound=parents_fixture(root);out=root/'out'
            with patch.object(m,'PARENT',parent),patch.object(m,'BOUND',bound),patch.object(m,'OUTPUT',out):
                ref=m.run(execute=True);d=json.loads(Path(ref['path']).read_bytes())
                self.assertEqual(d['projected_task_count'],2);self.assertFalse(d['risk_gate_recomputed'])
                self.assertEqual(set(p.name for p in out.iterdir()),{'started.json','tasks.jsonl','shared_control_aggregates.json','index.json','publication.json'})
                with self.assertRaises(ValueError):m.run(execute=True)
            failed=root/'failed';real=m.save
            def mutate(path,value):
                r=real(path,value)
                if path.name=='publication.json':
                    with (failed/'tasks.jsonl').open('ab') as f:f.write(b'{}\n')
                return r
            with patch.object(m,'PARENT',parent),patch.object(m,'BOUND',bound),patch.object(m,'OUTPUT',failed),patch.object(m,'save',side_effect=mutate):
                with self.assertRaisesRegex(ValueError,'JSONL'):m.run(execute=True)
                self.assertTrue((failed/'failure.json').exists())
                with self.assertRaises(ValueError):m.run(execute=True)

    def test_future_pins_and_audit_crosslinks(self):
        unbound=deepcopy(m.BOUND)
        unbound['index']=(unbound['index'][0],None)
        with patch.object(m,'BOUND',unbound),patch.object(Path,'read_bytes',side_effect=AssertionError('No read')):
            with self.assertRaises(ValueError):m.run(execute=True)
        with tempfile.TemporaryDirectory() as td:
            parent,bound=parents_fixture(Path(td));refs={k:m.ref(*v) for k,v in bound.items()}
            docs={k:json.loads(Path(refs[k]['path']).read_bytes()) for k in ('index','publication','audit')}
            m.validate_parents(**dict(index=docs['index'],pub=docs['publication'],audit=docs['audit'],refs=refs))
            docs['audit']['reader_sha256']='f'*64
            with self.assertRaises(ValueError):m.validate_parents(docs['index'],docs['publication'],docs['audit'],refs)

if __name__=='__main__':unittest.main()
