import json
from copy import deepcopy
import unittest
from scripts import ndx_first_cutoff_refit_independent_audit_20260919 as m


class Tests(unittest.TestCase):
    def data(self):return json.loads(m.CONTEXT.read_bytes()),json.loads(m.QUEUE.read_bytes()),json.loads(m.EXECUTION.read_bytes())['result']

    def test_bound_real_matrix_without_fit(self):
        context,queue,result=self.data();report=m.inspect_context(context,queue,result)
        self.assertEqual(report['fit_start'],'2022-09-30');self.assertEqual(report['fit_row_count'],126)
        self.assertTrue(report['correction_dates_outside_latest_fit'])
        self.assertTrue(all(report['decimal_risks']['checks'].values()))

    def test_bool_weight_nonzero_anchor_wrong_matrix_and_identity_reject(self):
        for defect in ('bool','nan','anchor','hash','identity'):
            context,queue,result=self.data();fitted=result['refit'];sid=next(iter(fitted['targets']))
            if defect=='bool':fitted['targets'][sid]['target_weight']=True
            if defect=='nan':fitted['targets'][sid]['target_weight']=float('nan')
            if defect=='anchor':fitted['anchor_by_security'][sid]=.1
            if defect=='hash':fitted['fit_data_sha256']='0'*64
            if defect=='identity':fitted['targets'][sid]['issuer_id']='wrong'
            with self.subTest(defect=defect),self.assertRaises(ValueError):m.inspect_context(context,queue,result)

    def test_other_typed_input_and_wrong_three_cells_reject(self):
        context,queue,result=self.data()
        context['prepared_inputs']['incumbent_weights']['payload']['mapping']['GOOG']={'float_hex':(.9).hex()}
        with self.assertRaises(ValueError):m.inspect_context(context,queue,result)
        context,queue,result=self.data();queue['input_binding']['corrections'][0]['new']=0.
        with self.assertRaises(ValueError):m.inspect_context(context,queue,result)


if __name__=='__main__':unittest.main()
