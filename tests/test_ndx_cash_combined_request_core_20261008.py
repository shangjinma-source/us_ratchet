from copy import deepcopy
import importlib,os,unittest
from test_ndx_cash_neighbor_selected_path_requests_research import fixture
from backtest import ndx_cash_neighbor_selected_path_requests_research as original
m=importlib.import_module(os.environ.get('CASH_REQUEST_MODULE','backtest.ndx_cash_neighbor_combined_selected_path_requests_research'))
class Tests(unittest.TestCase):
    def test_exact_original_request_semantics_native_combined_schema(self):
        arguments=fixture();baseline=original.prepare_selected_path_requests(**deepcopy(arguments))
        for case in arguments['cases']:case['selection']['schema']='CASH_NEIGHBOR_COMBINED_STREAM_SCENARIO_SELECTION_V1'
        before=deepcopy(arguments);actual=m.prepare_selected_path_requests(**arguments)
        for row in baseline['rows']:row['selection']['schema']='CASH_NEIGHBOR_COMBINED_STREAM_SCENARIO_SELECTION_V1'
        self.assertEqual(actual,baseline);self.assertEqual(arguments,before)
    def test_wrong_identity_vector_and_old_schema_rejected(self):
        for attack in ('schema','identity','vector'):
            case=fixture()['cases'][0];case['selection']['schema']='CASH_NEIGHBOR_COMBINED_STREAM_SCENARIO_SELECTION_V1'
            if attack=='schema':case['selection']['schema']='CASH_NEIGHBOR_STREAM_SCENARIO_SELECTION_V1'
            elif attack=='identity':case['selection']['selected']['identity']['task_id']='f'*64
            else:case['selection']['selected']['buy_shares']['A']+=1
            with self.subTest(attack=attack),self.assertRaises(ValueError):m.prepare_case(case,0)
if __name__=='__main__':unittest.main()
