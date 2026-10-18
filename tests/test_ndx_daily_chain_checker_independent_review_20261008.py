from copy import deepcopy
import unittest
from unittest.mock import patch
from backtest import ndx_multidecision_daily_chain_inspection_research as checker
from backtest import ndx_multidecision_daily_chain_projection_research as producer
from backtest import ndx_saved_chain_weight_aggregation_research as aggregation
from test_ndx_multidecision_daily_chain_projection_research import fixture


class Review(unittest.TestCase):
    def test_no_hidden_renormalization_and_no_producer_execution(self):
        args=fixture();day=args['supplement_document']['supplement']['original_raw_bundles_preserved']['control'][1]['document']['result']['daily'][119]
        day.update(shares={'SID':1,'SID2':1},risk={'actual_weights':{'SID':0.7,'SID2':0.4}},risk_chains={'SID':'X','SID2':'X'},risk_chain_observation_dates=dict.fromkeys(('SID','SID2'),day['session']))
        result=producer.build_chain_projection(**args,aggregate_saved_weights=aggregation.aggregate_saved_weights)
        with patch.object(producer,'build_chain_projection',side_effect=AssertionError('forbidden')),patch.object(aggregation,'aggregate_saved_weights',side_effect=AssertionError('forbidden')):
            report=checker.inspect_chain_projection(projection=result,**args)
        self.assertEqual(report['day_count'],2880)
        self.assertEqual(result['paths'][17]['rows'][-1]['chain_weights']['X'],{'numerator':'11','denominator':'10'})

    def test_last_cells_in_each_table_and_locator_or_basis_corruption(self):
        args=fixture();result=producer.build_chain_projection(**args,aggregate_saved_weights=aggregation.aggregate_saved_weights)
        for table in range(4):
            bad=deepcopy(result);bad['tables'][table]['rows'].pop()
            with self.subTest(table=table),self.assertRaises(ValueError):checker.inspect_chain_projection(projection=bad,**args)
        for key,value in [('basis','ORIGINAL_SAVED'),('chain_weights',{}),('source_locator',{'reference':{'path':'other','sha256':'a'*64}})]:
            bad=deepcopy(result);bad['paths'][-1]['rows'][-1][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):checker.inspect_chain_projection(projection=bad,**args)


if __name__=='__main__':unittest.main()
