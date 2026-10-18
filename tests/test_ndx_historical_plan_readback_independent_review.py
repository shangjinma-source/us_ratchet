import copy
import itertools
import json
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts import ndx_historical_fourteen_plan_independent_audit_20260923 as m


class HistoricalPlanReadbackReview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document=json.loads(Path(m.INPUT['path']).read_bytes())
        cls.target=json.loads(Path(m.TARGET['path']).read_bytes())

    def test_first_task_identity_tamper_rejected_before_rest_of_denominator(self):
        frame=m.first_window(self.document);params=m.target_reader.scalar.PARAMS
        numerical=self.target['result']['source_hashes']
        first=next(m.independent_rows(self.document,params,frame,numerical))
        for defect in ('cutoff','prior','reference','matrix','parameter'):
            row=copy.deepcopy(first)
            if defect=='cutoff':row['task']['cutoff']='2026-09-17'
            elif defect=='prior':row['task']['previous_target_weights']={}
            elif defect=='reference':row['completed_external_reference']=m.TARGET
            elif defect=='matrix':row['fit_data_sha256']='0'*64
            else:row['task']['parameters']['fit_days']=125
            value={'tasks':[row]*31828}
            with self.subTest(defect=defect),self.assertRaises(ValueError):
                m.inspect(value,self.document,self.target,params,numerical,{}, {},50000)

    def test_reference_is_single_historical_identity_not_a_new_result(self):
        frame=m.first_window(self.document);task=self.target['task'];sources=self.target['result']['source_hashes']
        row=m.expected_task(task['selected'],task['weight_spec'],task['parameters'],frame,sources)
        self.assertEqual(row['task_id'],m.target_reader.JOB)
        self.assertFalse(row['result_reused']);self.assertNotIn('result',row)
        altered=copy.deepcopy(frame);altered['data'][0][0]+=.01
        # Fingerprint changes independently even when task structure stays fixed.
        selected={s:dict(v) for s,v in task['selected'].items()}
        chosen=next(iter(selected.values()))['ticker'];index=frame['columns'].index(chosen)
        altered=copy.deepcopy(frame);altered['data'][0][index]+=.01
        other=m.expected_task(selected,task['weight_spec'],task['parameters'],altered,sources)
        self.assertNotEqual(row['input_equivalence_sha256'],other['input_equivalence_sha256'])

    def test_report_publication_cannot_resign_missing_sources_or_upgrade_import(self):
        value=dict(schema='HISTORICAL_FOURTEEN_PLAN_INDEPENDENT_AUDIT_V1',historical_expected_source_hashes={'required':'a'*64},archive_resolution={},latest_results_imported=False,result_imported=False)
        for key,replacement in [('historical_expected_source_hashes',{}),('latest_results_imported',True),('result_imported',0)]:
            bad=copy.deepcopy(value);bad[key]=replacement
            with self.subTest(key=key),patch.object(m,'build',return_value=value),patch.object(m,'publish') as publisher:
                with self.assertRaises(ValueError):m.publish_verified('unused.json',bad)
                publisher.assert_not_called()


if __name__=='__main__':unittest.main()
