from copy import deepcopy
import unittest
from scripts import ndx_dated_account_input_independent_readback_20261003 as reader
from scripts import ndx_dated_account_inputs_20261003 as producer
from backtest import ndx_dated_account_input_research as pure
from test_ndx_dated_account_inputs_20261003 import documents
from test_ndx_dated_account_input_research import REF

def fixture():
    a,parents=documents();document=producer.project(pure,a['task'],dict(REF,json_pointer='/task'),a['fit_result'],REF,parents)
    for i,row in enumerate(parents['registry']['events']):
        if not row:parents['registry']['events'][i]=dict(ticker='UNRELATED'+str(i),first_adjusted_trading_date='2020-01-01')
    parents['preparation']={'task':a['task']};parents['raw']={'fitted':a['fit_result']};parents['channels']['calendar253']=next(iter(a['candidate_channels_by_security'].values()))['calendar']
    return document,parents

class Tests(unittest.TestCase):
    def test_complete_synthetic_quotes_and_originals(self):
        d,p=fixture();before=deepcopy(d);r=reader.inspect(d,p);self.assertEqual(r['quote_value_count'],10*127*2);self.assertEqual(r['split_event_count'],2);self.assertEqual(d,before)
    def test_price_alias_weight_split_attacks(self):
        for what in ('matrix','alias','weight','event','exact'):
            d,p=fixture();a=d['inputs']['candidate'];sid=a['original_security_order'][0]
            if what=='matrix':a['matrices']['open']['data'][0][0]+=1
            elif what=='alias':a['engine_ticker_by_security'][sid]='SID_OTHER'
            elif what=='weight':a['schedule'][0]['targets'][sid]['target_weight']=.6
            elif what=='event':a['corporate_actions'][0]['new_shares']=2
            else:a['exact_quote_conversion_evidence'][sid][0]['close']['exact']='101/2'
            with self.subTest(what=what),self.assertRaises(ValueError):reader.inspect(d,p)
    def test_risk_parameters_and_execution_semantics(self):
        for field,value in [('risk_parameters',{}),('split_application_order','AFTER_PURCHASE'),('engine_weight_semantics','RENORMALIZE_CONTROL')]:
            d,p=fixture();d['inputs']['incumbent'][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):reader.inspect(d,p)

if __name__=='__main__':unittest.main()
