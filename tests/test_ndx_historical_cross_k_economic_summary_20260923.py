import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import ndx_historical_cross_k_economic_summary_20260923 as m


class SummaryTests(unittest.TestCase):
    def test_exact_pareto_keeps_ties_and_cash(self):
        def row(name,values):
            return dict(task_id=name,pareto_coordinates=values,metrics={},benchmark_metrics={},target_k=4,outcome='FILLED')
        rows=[row('a',['1','0','1','0']),row('b',['1','0','1','0']),row('c',['0','1','0','1']),row('d',['0','0','0','0'])]
        self.assertEqual(m.pareto(rows),['a','b','c'])
        rows[2]['outcome']='NO_PLAN'
        result=m.aggregate(rows,4)
        self.assertIn('c',result['all_account_pareto_task_ids'])
        self.assertNotIn('c',result['filled_account_pareto_task_ids'])
        with self.assertRaises(ValueError):m.aggregate(rows,3)
        with self.assertRaises(ValueError):m.aggregate(rows+[rows[0]],5)
        with self.assertRaises(ValueError):m.number(False)
        with self.assertRaises(ValueError):m.number('NaN')

    def test_saved_real_shapes_only_no_source_audit_or_engine(self):
        self.assertEqual(m.sha(m.AUDIT),m.AUDIT_SHA)
        audit=json.loads(m.AUDIT.read_text(encoding='utf-8'));seen=set()
        for detail in audit['details']:
            saved=json.loads(Path(detail['result_reference']['path']).read_text(encoding='utf-8'))
            statuses=tuple(d['status'] for d in saved['execution']['decisions'])+tuple(d['status'] for d in saved['execution']['executions'])
            if statuses in seen:continue
            seen.add(statuses)
            raw=json.loads(Path(detail['raw_reference']['path']).read_text(encoding='utf-8'))
            row=m.summarize_detail(detail,saved,raw)
            self.assertIn(row['outcome'],('FILLED','NO_PLAN','REJECTED'))
        self.assertEqual(len(seen),3)

    def test_refuses_tampered_summary_and_wrong_authority(self):
        with self.assertRaises(ValueError):m.build(audit_sha256='0'*64)
        expected={'rows':[],'winner_selected':False,'historical_expected_source_hashes':{'x':'y'}}
        with patch.object(m,'build',return_value=expected):
            for key,value in [('winner_selected',True),('historical_expected_source_hashes',{}),('rows',[{}])]:
                bad=copy.deepcopy(expected);bad[key]=value
                with self.assertRaises(ValueError):m.verify(bad)


if __name__=='__main__':unittest.main()
