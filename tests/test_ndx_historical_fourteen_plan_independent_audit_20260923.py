import copy
from fractions import Fraction
import json
from pathlib import Path
import unittest
from scripts import ndx_historical_fourteen_plan_independent_audit_20260923 as m


class PlanReadbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document=json.loads(Path(m.INPUT['path']).read_bytes())
        cls.target=json.loads(Path(m.TARGET['path']).read_bytes())

    def test_exact_original_historical_job_and_selected_matrix(self):
        frame=m.first_window(self.document);task=self.target['task']
        row=m.expected_task(task['selected'],task['weight_spec'],task['parameters'],frame,self.target['result']['source_hashes'])
        self.assertEqual(row['task_id'],m.target_reader.JOB)
        self.assertEqual(row['fit_data_sha256'],self.target['result']['fit_data_sha256'])
        self.assertEqual(row['completed_external_reference'],m.TARGET)
        self.assertFalse(row['result_reused'])
        equal=m.expected_task(task['selected'],'equal_weight',task['parameters'],frame,self.target['result']['source_hashes'])
        self.assertIsNone(equal['completed_external_reference']);self.assertEqual(equal['status'],'PENDING_HISTORICAL_FIT')

    def test_future_rows_do_not_enter_and_historical_cell_does(self):
        before=m.first_window(self.document);altered=copy.deepcopy(self.document)
        altered['prices']['returns']['data'][-1][0]=999.
        self.assertEqual(before,m.first_window(altered))
        ticker=before['columns'][0];position=altered['prices']['returns']['columns'].index(ticker)
        altered['prices']['returns']['data'][0][position]+=.001
        self.assertNotEqual(before,m.first_window(altered))
        altered=copy.deepcopy(self.document);altered['prices']['returns']['index'][0]='2025-09-17T01:00:00'
        with self.assertRaises(ValueError):m.first_window(altered)

    def test_all_k_bounds_and_fraction_certificate_algebra(self):
        params=m.target_reader.scalar.PARAMS
        proofs={k:m.independent_certificates(k,params) for k in range(1,15)}
        self.assertEqual([k for k,p in proofs.items() if p],[1,2,3])
        self.assertEqual(sum(m.math.comb(14,k) for k in range(1,15)),16383)
        self.assertEqual(sum(m.math.comb(14,k) for k in proofs if proofs[k]),469)
        self.assertEqual(2*sum(m.math.comb(14,k) for k in proofs if not proofs[k]),31828)
        for entries in proofs.values():
            for row in entries:
                f=lambda value:Fraction(int(value['numerator']),int(value['denominator']))
                self.assertEqual(abs(f(row['left'])-f(row['right'])),f(row['strict_gap']))
                self.assertTrue(f(row['left'])<f(row['right']) if row['comparison']=='<' else f(row['left'])>f(row['right']))

    def test_missing_provenance_future_fit_and_unsealed_plan_rejected(self):
        for defect in ('provenance','dates','duplicateissuer'):
            doc=copy.deepcopy(self.document)
            if defect=='provenance':doc['candidate_full_original_provenance'].pop()
            elif defect=='dates':doc['prices']['fit_return_dates']=doc['prices']['evaluation_return_dates']
            else:doc['candidate_coordinate_and_risk_rows'][1]['issuer_id']=doc['candidate_coordinate_and_risk_rows'][0]['issuer_id']
            with self.subTest(defect=defect),self.assertRaises(ValueError):m.first_window(doc)
        from unittest.mock import patch
        with patch.object(m,'PLAN_SHA',None),self.assertRaisesRegex(ValueError,'Await'):m.build()


if __name__=='__main__':unittest.main()
