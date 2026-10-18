import io
import unittest
from copy import deepcopy
from pathlib import Path
import tempfile
from unittest.mock import patch
from scripts import ndx_dated_risk_chain_display_20261003 as m
from test_ndx_dated_risk_chain_display_20261003 import fixture_stream,parents_fixture,core

class Tests(unittest.TestCase):
    def test_display_preserves_targets_missing_denominator_and_dedup(self):
        index,shared,blob=fixture_stream();before=deepcopy((index,shared));rows=[]
        output=m.project_stream(io.BytesIO(blob),index,shared,core,lambda r:rows.append(r) or {'ordinal':len(rows)-1})
        self.assertEqual((index,shared),before)
        self.assertEqual(len(output['task_index']),1632)
        self.assertEqual(sum(r['planned_task_count'] for r in output['k_spec_coverage']),1632)
        self.assertEqual(sum(r['not_supplied_task_count'] for r in output['k_spec_coverage']),1630)
        self.assertEqual(len(output['shared_control_aggregates']),2)
        originals=[m.loads(line) for line in blob.splitlines()]
        for row,old in zip(rows,originals):
            self.assertEqual(row['targets']['candidate']['source_evidence'],old['target_evidence']['candidate'])
            self.assertEqual(row['targets']['incumbent']['source_evidence'],old['target_evidence']['incumbent'])
            self.assertEqual(row['original_task_summary_row'],old['original_task_summary_row'])
            self.assertFalse(row['economics_recomputed']);self.assertFalse(row['point_in_time_verified'])
        self.assertIsNone(rows[1]['tracks']['candidate_integer']['rows'])
        self.assertEqual(len(rows[1]['tracks']['candidate_integer']['calendar_slots']),127)
    def test_entry_stratum_and_calendar_cannot_disagree(self):
        for mode in ('wrong_k','bool_k','layer_count','calendar'):
            index,shared,blob=fixture_stream()
            if mode=='wrong_k':index['task_index'][0]['k']=5
            elif mode=='bool_k':index['task_index'][-1]['k']=True
            elif mode=='layer_count':index['task_index'][-1]['weight_spec']=index['task_index'][0]['weight_spec']
            else:index['calendar']=index['calendar'][:-1]
            with self.subTest(mode=mode),self.assertRaises(ValueError):m.project_stream(io.BytesIO(blob),index,shared,core,lambda r:None)
    def test_audit_false_flags_and_late_dependency_drift(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);parent,bound=parents_fixture(root);refs={k:m.ref(*r) for k,r in bound.items()}
            docs={k:m.loads(Path(refs[k]['path']).read_bytes()) for k in ('index','publication','audit')}
            docs['audit']['risk_recomputed']=0
            with self.assertRaises(ValueError):m.validate_parents(docs['index'],docs['publication'],docs['audit'],refs)
            out=root/'out';real=m.save
            def mutate(path,value):
                r=real(path,value)
                if path.name=='publication.json':Path(bound['reader'][0]).write_bytes(b'# source changed')
                return r
            with patch.object(m,'BOUND',bound),patch.object(m,'PARENT',parent),patch.object(m,'OUTPUT',out),patch.object(m,'save',side_effect=mutate):
                with self.assertRaisesRegex(ValueError,'Source drift'):m.run(execute=True)
                self.assertTrue((out/'failure.json').exists())
                with self.assertRaises(ValueError):m.run(execute=True)

if __name__=='__main__':unittest.main()
