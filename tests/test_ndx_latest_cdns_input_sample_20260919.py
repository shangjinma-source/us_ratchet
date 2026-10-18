import copy,json,unittest
from unittest.mock import patch
from scripts import ndx_latest_cdns_input_sample_20260919 as m
from test_ndx_latest_amat_input_independent_review import fixture as original_fixture

def fixture():
    args,body,days=original_fixture();body['chart']['result'][0]['meta']['symbol']='CDNS'
    for row in args['quote_rows']:row['ticker']='CDNS'
    args['decoded']=json.dumps(body).encode();return args,body,days

class Tests(unittest.TestCase):
    def test_conditional_ratio_one_126_returns_63_actual_volume(self):
        args,body,days=fixture();v=m.calculate(**args)
        self.assertEqual(len(v['price_returns']['rows']),126);self.assertEqual(len(v['liquidity_rows']),63)
        self.assertEqual(v['price_returns']['rows'][-1]['price_return'],-.5)
        self.assertEqual(v['median_dollar_volume_usd'],'100000000.0')
        self.assertFalse(v['liquidity_legality_or_corporate_action_unit_independently_certified'])
        m.validate_numerical(v)
        body['chart']['result'][0]['events']['dividends']={'cash':{'amount':100}}
        changed=m.calculate(**dict(args,decoded=json.dumps(body).encode()))
        self.assertEqual(v['price_returns'],changed['price_returns'])

    def test_nested_units_and_kernel_scope_cannot_upgrade(self):
        original=m.calculate(**fixture()[0])
        for defect in ('unit','basis','kernel_flag','ratio','count','median'):
            n=copy.deepcopy(original)
            if defect=='unit':n['liquidity_legality_or_corporate_action_unit_independently_certified']=True
            if defect=='basis':n['liquidity_basis']='OFFICIAL_ADJUSTED_VOLUME'
            if defect=='kernel_flag':n['price_returns']['event_completeness_independently_verified']=True
            if defect=='ratio':n['input_payload']['daily_share_ratios'][0]['new_shares']=True
            if defect=='count':n['price_returns']['output_return_count']=127
            if defect=='median':n['median_dollar_volume_usd']='1'
            with self.subTest(defect=defect),self.assertRaises(ValueError):m.validate_numerical(n)

    def test_no_event_deletion_or_implicit_unit_conversion(self):
        for defect in ('split','unknown_event','volume_bool','factor','ticker','interior'):
            args,body,days=fixture();data=body['chart']['result'][0]
            if defect=='split':data['events']['splits']={'old':{'numerator':2,'denominator':1}}
            if defect=='unknown_event':data['events']['spinoff']={}
            if defect=='volume_bool':data['indicators']['quote'][0]['volume'][-1]=True
            if defect=='factor':args['quote_rows'][-1]['split_factor']=2
            if defect=='ticker':data['meta']['symbol']='AMAT'
            if defect=='interior':args['reference'].pop(-20);args['reference'].insert(0,days[0])
            args['decoded']=json.dumps(body).encode()
            with self.subTest(defect=defect),self.assertRaises(ValueError):m.calculate(**args)

    def test_official_history_or_execution_upgrade_rejected_before_source_read(self):
        value=dict(action_evidence_scope='ONLY_RETURNED_RAW_EVENTS_CONDITIONAL_RATIO_ONE',official_action_table_verified=False,record_date_used_as_ex_date=False,execution_authorized=False)
        for key in ('official_action_table_verified','record_date_used_as_ex_date','execution_authorized'):
            bad=dict(value);bad[key]=True
            with self.subTest(key=key),self.assertRaises(ValueError):m.verify(bad)
        with self.assertRaises(ValueError):m.verify(dict(value,action_evidence_scope='OFFICIAL_NO_SPLITS_CERTIFIED'))

if __name__=='__main__':unittest.main()
