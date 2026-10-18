import copy
import itertools
import json
import math
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts import ndx_historical_fourteen_cross_k_plan_20260923 as m


def fixture():
    return json.loads(Path(m.INPUT['path']).read_bytes()),json.loads(Path(m.TARGET['path']).read_bytes())


def completed_row(panel,target):
    task={k:v for k,v in target['task'].items() if k!='task_id'}
    tickers=[task['selected'][sid]['ticker'] for sid in sorted(task['selected'])]
    matrix=m.digest(dict(dates=[d.date().isoformat() for d in panel['returns'].index],tickers=tickers,returns=panel['returns'][tickers].to_numpy().tolist()))
    return dict(task=task,task_id=m.digest(task),fit_data_sha256=matrix,input_equivalence_sha256=m.digest(dict(task=task,fit_data_sha256=matrix,fitter_source_hashes=target['result']['source_hashes'])))


class HistoricalCrossKReview(unittest.TestCase):
    def test_complete_small_issuer_combinations_and_two_specs_no_prior(self):
        document,_=fixture();panel=m.historical_view(document)
        panel['universe']=panel['universe'].iloc[:5].copy()
        tickers=panel['universe']['ticker'].tolist()
        for key in ('returns','nominal_close'):panel[key]=panel[key][tickers].copy()
        panel['panel_content_sha256']=m.enumeration.core.panel_digest(panel)
        cards,tasks=m.enumeration.enumerate_inputs(panel,m.target_reader.scalar.PARAMS,{'source':'a'*64})
        self.assertEqual([row['combinations'] for row in cards],[math.comb(5,k) for k in range(1,6)])
        self.assertEqual([bool(row['necessary_bound_certificates']) for row in cards],[True,True,True,False,False])
        ids=sorted(panel['universe']['security_id'])
        expected={(tuple(selection),spec) for k in (4,5) for selection in itertools.combinations(ids,k) for spec in ('equal_weight','constrained_fixed_shrinkage')}
        actual={(tuple(sorted(row['task']['selected'])),row['task']['weight_spec']) for row in tasks}
        self.assertEqual(actual,expected);self.assertEqual(len(tasks),12)
        self.assertTrue(all(row['task']['previous_target_weights'] is None and row['task']['cutoff']=='2026-03-18' for row in tasks))

    def test_future_data_never_changes_historical_tasks_and_latest_job_cannot_enter(self):
        document,target=fixture();panel=m.historical_view(document)
        future=copy.deepcopy(document)
        for row in future['prices']['returns']['data'][126:]:row[:]=[100.] * len(row)
        self.assertTrue(panel['returns'].equals(m.historical_view(future)['returns']))
        for defect in ('latest','duplicate','matrix'):
            changed=copy.deepcopy(target);rows=[completed_row(panel,target)]
            if defect=='latest':
                changed['task']['cutoff']='2026-09-17'
                changed['task']['task_id']=m.digest({k:v for k,v in changed['task'].items() if k!='task_id'})
                changed['job_id']=changed['task']['task_id']
            elif defect=='duplicate':rows.append(copy.deepcopy(rows[0]))
            else:rows[0]['fit_data_sha256']='0'*64
            with self.subTest(defect=defect),self.assertRaises(ValueError):m.attach_completed_reference(rows,changed,target['result']['source_hashes'],panel)

    def test_verify_refuses_relabelled_reference_import_and_deleted_source(self):
        baseline=dict(historical_expected_source_hashes={'required':'a'*64},result_imported=False,completed_external_reference_count=1)
        for key,value in [('result_imported',True),('completed_external_reference_count',764),('historical_expected_source_hashes',{})]:
            changed=copy.deepcopy(baseline);changed[key]=value
            with self.subTest(key=key),patch.object(m,'build',return_value=baseline),self.assertRaises(ValueError):m.verify(changed)


if __name__=='__main__':unittest.main()
