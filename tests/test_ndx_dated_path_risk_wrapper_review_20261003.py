from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_dated_path_risk_display_20261003 as m
from backtest import ndx_dated_path_risk_display_research as core
from test_ndx_dated_path_risk_display_wrapper_20261003 import summary_fixture
from test_ndx_dated_path_risk_display_research import fixture

class ReviewTests(unittest.TestCase):
    def test_all_51_strata_missing_and_all_cash_distinct(self):
        summary=summary_fixture()
        for i,row in enumerate(summary['rows']):
            row['k']=4+i//96;row['weight_spec']=('equal','fixed','turnover')[i//32%3]
        ids=[r['numerical_task_id'] for r in summary['rows']]
        envelopes={ids[0]:fixture(first=True),ids[-1]:fixture(task_id=ids[-1],missing=True)}
        emitted=[]
        out=m.stream_paths(summary,{t:{} for t in envelopes},lambda t,r:deepcopy(envelopes[t]),core,lambda row:emitted.append(row) or dict(record_index=len(emitted)-1))
        self.assertEqual(len(out['k_spec_coverage']),51)
        self.assertTrue(all(r['planned_task_count']==32 for r in out['k_spec_coverage']))
        self.assertEqual(sum(r['not_supplied_task_count'] for r in out['k_spec_coverage']),1630)
        self.assertEqual(len(emitted[0]['tracks']['candidate_integer']['path']),127)
        self.assertIsNone(emitted[1]['tracks']['candidate_integer']['path'])
        self.assertEqual(len(out['shared_paths']),4)
        self.assertFalse(out['risk_recomputed'])

    def test_callback_cannot_attach_valid_other_task_to_index(self):
        summary=summary_fixture();other=summary['rows'][1]['numerical_task_id'];writes=[]
        with self.assertRaises(ValueError):
            m.stream_paths(summary,{m.FIRST:{}},lambda t,r:fixture(task_id=other),core,lambda row:writes.append(row))
        self.assertEqual(writes,[])

    def test_jsonl_drift_during_publication_retained_as_failure(self):
        summary=summary_fixture();docs=dict(task_summary=summary,batch=dict(failure=None,unresolved_task_ids=[],undispatched_task_ids=[]))
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)/'out';save=m.save
            def mutate(path,value):
                ref=save(path,value)
                if path.name=='publication.json':
                    with (out/'tasks.jsonl').open('ab') as stream:stream.write(b'{}\n')
                return ref
            with patch.object(m,'OUTPUT',out),patch.object(m,'load_inputs',return_value=(docs,{m.FIRST:{}},{},core)),patch.object(m,'load_projection_inputs',return_value=fixture(first=True)),patch.object(m,'guard'),patch.object(m,'save',side_effect=mutate):
                with self.assertRaisesRegex(ValueError,'JSONL'):m.run(execute=True)
                self.assertTrue((out/'failure.json').exists())
                with self.assertRaises(ValueError):m.run(execute=True)

if __name__=='__main__':unittest.main()
