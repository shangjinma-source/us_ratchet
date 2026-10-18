from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_dated_path_risk_display_20261003 as m
from backtest import ndx_dated_path_risk_display_research as core
from test_ndx_dated_path_risk_display_research import fixture


def summary_fixture():
    ids=[m.FIRST]+[format(i,'064x') for i in range(1,1632)]
    return dict(rows=[dict(numerical_task_id=t,k=4,weight_spec='equal') for t in ids],full_new_cutoff_task_denominator=6222659648236112670)


class Tests(unittest.TestCase):
    def test_sparse_full_order_first_new_missing_and_shared_once(self):
        summary=summary_fixture(); ids=[r['numerical_task_id'] for r in summary['rows']]
        envelopes={ids[0]:fixture(first=True),ids[8]:fixture(task_id=ids[8],missing=True)}
        before=deepcopy(envelopes);rows=[]
        result=m.stream_paths(summary,dict.fromkeys(envelopes,{}),lambda t,r:envelopes[t],core,lambda r:rows.append(r) or {'record_index':len(rows)-1})
        self.assertEqual(result['planned_task_count'],1632)
        self.assertEqual(result['projected_task_count'],2)
        self.assertEqual(result['not_supplied_task_count'],1630)
        self.assertEqual(len(result['shared_paths']),4)
        self.assertEqual([r['numerical_task_id'] for r in rows],[ids[0],ids[8]])
        self.assertIsNone(rows[1]['tracks']['candidate_integer']['path'])
        self.assertEqual(rows[0]['tracks']['candidate_integer']['decisions'],[{'status':'NO_PLAN'}])
        self.assertEqual(rows[1]['preserved_evidence_sidecars'],{'all7':'preserved'})
        self.assertEqual(envelopes,before)

    def test_shared_conflict_and_foreign_task_rejected(self):
        summary=summary_fixture();tid=summary['rows'][1]['numerical_task_id']
        a=fixture(first=True);b=fixture(task_id=tid)
        b['document']['comparison']['tracks']['incumbent_continuous']['original_track_preserved']['path'][1]['extra']='drift'
        with self.assertRaises(ValueError):m.stream_paths(summary,{m.FIRST:{},tid:{}},lambda t,r:a if t==m.FIRST else b,core,lambda r:None)
        with self.assertRaises(ValueError):m.stream_paths(summary,{'foreign':{}},lambda t,r:None,core,lambda r:None)
        with self.assertRaises(ValueError):m.merge({'x':'a'},'x','b')

    def test_publication_stream_and_failure_are_create_only(self):
        summary=summary_fixture();docs=dict(task_summary=summary,batch=dict(failure=None,unresolved_task_ids=[],undispatched_task_ids=[]))
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'out'
            with patch.object(m,'OUTPUT',out),patch.object(m,'load_inputs',return_value=(docs,{m.FIRST:{}},{},core)),patch.object(m,'load_projection_inputs',return_value=fixture(first=True)),patch.object(m,'guard'):
                ref=m.run(execute=True)
                index=json.loads(Path(ref['path']).read_bytes())
                line=(out/'tasks.jsonl').read_bytes()
                self.assertEqual(index['task_jsonl_reference']['sha256'],m.sha(line))
                self.assertEqual(index['task_index'][0]['jsonl_record']['byte_stop'],len(line))
                self.assertEqual(len(json.loads((out/'shared_paths.json').read_bytes())['shared_paths']),4)
                with self.assertRaises(ValueError):m.run(execute=True)
            failed=Path(tmp)/'failed'
            with patch.object(m,'OUTPUT',failed),patch.object(m,'load_inputs',return_value=(docs,{m.FIRST:{}},{},core)),patch.object(m,'load_projection_inputs',side_effect=ValueError('item drift')),patch.object(m,'guard'):
                with self.assertRaises(ValueError):m.run(execute=True)
                self.assertTrue((failed/'failure.json').exists())
                self.assertFalse((failed/'publication.json').exists())
                with self.assertRaises(ValueError):m.run(execute=True)

    def test_pending_pin_cannot_publish(self):
        bound=deepcopy(m.BOUND);bound['batch']=(bound['batch'][0],None)
        with tempfile.TemporaryDirectory() as tmp,patch.object(m,'OUTPUT',Path(tmp)/'output'),patch.object(m,'BOUND',bound):
            with self.assertRaises(ValueError):m.run(execute=True)
            self.assertFalse(m.OUTPUT.exists())


if __name__=='__main__':unittest.main()
