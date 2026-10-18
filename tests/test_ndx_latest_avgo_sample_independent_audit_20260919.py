import json
import unittest
from test_ndx_latest_goog_sample_independent_audit_20260919 import fixture as original,RECEIPT
from scripts import ndx_latest_avgo_sample_independent_audit_20260919 as m


def fixture():
    sample,raw=original()
    text=json.dumps(sample).replace('GOOG','AVGO').replace('0001652044','0001730168').replace('02079K107','11135F101').replace('1658151000','1721050200').replace('2022-07-18','2024-07-15').replace('20:1','10:1').replace('"20.0"','"10.0"')
    sample=json.loads(text)
    raw=raw.replace(b'GOOG',b'AVGO').replace(b'1658151000',b'1721050200').replace(b'20.0',b'10.0').replace(b'20:1',b'10:1')
    sample['returned_raw_events']=json.loads(raw)['chart']['result'][0]['events']
    sample['numerical']['observed_historical_split']['new_shares']=10
    n=sample['numerical'];n['independent_decimal_return_max_error']='0'
    n['input_payload'].update(schema='ndx_split_neutral_return_input_v1',event_denominator_scope='EXPLICIT_ALL_SUBMITTED_SECURITY_SESSIONS')
    n['price_returns'].update(schema='ndx_split_neutral_price_return_research_v1',basis='NOMINAL_CLOSE',event_denominator_scope='EXPLICIT_ALL_SUBMITTED_SECURITY_SESSIONS',security_count=1,input_price_row_count=127,explicit_event_cell_count=127,output_return_count=126,first_session_has_no_previous_close_return=True,**dict.fromkeys(('dividend_cash_flows_included','source_assertions_authenticated','event_completeness_independently_verified','stable_coordinate_authenticity_verified','calendar_exchange_completeness_verified','old_training_reuse_authorized','execution_price_use_authorized','point_in_time_verified','promotion_allowed'),False))
    sample.update(old_pre_redomiciliation_issuer_or_cusip_continuity_inferred=False,official_specific_split_facts=dict(ticker='AVGO',security_class='COMMON_STOCK',new_shares=10,old_shares=1,first_adjusted_session='2024-07-15',declared_effective_date='2024-07-12',first_adjusted_date_declaration='EXPECTED_IN_ISSUER_FAQ',actual_execution_independently_reconfirmed=False,old_pre_redomiciliation_issuer_or_cusip_continuity_inferred=False,corporate_action_completeness_verified=False))
    return sample,raw


class Tests(unittest.TestCase):
    def test_nested_counts_schema_and_error_finite(self):
        for defect in ('boolcount','schema','first','nan','negative'):
            sample,raw=fixture();n=sample['numerical']
            if defect=='boolcount':n['price_returns']['security_count']=True
            if defect=='schema':n['price_returns']['schema']='other'
            if defect=='first':n['price_returns']['first_session_has_no_previous_close_return']=False
            if defect=='nan':n['independent_decimal_return_max_error']='NaN'
            if defect=='negative':n['independent_decimal_return_max_error']='-1'
            with self.subTest(defect=defect),self.assertRaises(ValueError):m.inspect(sample,raw,RECEIPT)

    def test_independent_latest_unit_and_full_denominator(self):
        sample,raw=fixture();result=m.inspect(sample,raw,RECEIPT)
        self.assertEqual(result['return_count'],126);self.assertEqual(result['liquidity_count'],63)
        self.assertEqual(result['median_dollar_volume_usd'],'100000000')

    def test_effective_trading_and_unproved_identity_distinct(self):
        for defect in ('effective','trading','actual','oldissuer','unit','receipt'):
            sample,raw=fixture();fact=sample['official_specific_split_facts']
            if defect=='effective':fact['declared_effective_date']='2024-07-15'
            if defect=='trading':fact['first_adjusted_session']='2024-07-12'
            if defect=='actual':fact['actual_execution_independently_reconfirmed']=True
            if defect=='oldissuer':sample['old_pre_redomiciliation_issuer_or_cusip_continuity_inferred']=True
            if defect=='unit':sample['numerical']['liquidity_rows'][-1]['dollar_volume']='1000000000'
            if defect=='receipt':sample['receipt_day_excluded']='2026-09-19'
            with self.subTest(defect=defect),self.assertRaises(ValueError):m.inspect(sample,raw,RECEIPT)

    def test_malformed_raw_split_or_wrong_daily_return_reject(self):
        for defect in ('delete','negative','bool','extra','return'):
            sample,raw=fixture();data=json.loads(raw);events=data['chart']['result'][0]['events']['splits'];event=events['1721050200']
            if defect=='delete':events.clear()
            if defect=='negative':event.update(numerator=-10,denominator=-1)
            if defect=='bool':event['denominator']=True
            if defect=='extra':events['another']=dict(event)
            if defect=='return':sample['numerical']['price_returns']['rows'][-1]['price_return']=.1
            with self.subTest(defect=defect),self.assertRaises(ValueError):m.inspect(sample,json.dumps(data).encode(),RECEIPT)


if __name__=='__main__':unittest.main()
