import json
import unittest
from test_ndx_latest_amat_sample_independent_audit_20260919 import fixture as original
from scripts import ndx_latest_goog_sample_independent_audit_20260919 as m
RECEIPT=dict(received_at_utc='2026-09-18T19:00:00+00:00',completed_training_excludes_dates_on_or_after='2026-09-18')


def fixture():
    sample,raw=original()
    sample=json.loads(json.dumps(sample).replace('AMAT','GOOG').replace('0000006951','0001652044').replace('038222105','02079K107'))
    data=json.loads(raw);data['chart']['result'][0]['meta']['symbol']='GOOG'
    events={'splits':{'1658151000':dict(date=1658151000,numerator=20.0,denominator=1.0,splitRatio='20:1')}}
    data['chart']['result'][0]['events']=events
    sample.update(historical_split_event_removed=False,returned_raw_events=events,official_specific_split_facts=dict(ticker='GOOG',security_class='CLASS_C_CAPITAL',new_shares=20,old_shares=1,first_adjusted_session='2022-07-18',separately_reported_execution_date='2022-07-15',first_adjusted_date_declaration='EXPECTED_IN_APPROVED_8K',corporate_action_completeness_verified=False))
    sample['received_at_utc']=RECEIPT['received_at_utc']
    sample['numerical'].update(observed_historical_split=dict(first_adjusted_session='2022-07-18',new_shares=20,old_shares=1,raw_event=dict(date=1658151000,numerator='20.0',denominator='1.0',splitRatio='20:1')),liquidity_legality_or_corporate_action_unit_independently_certified=False,liquidity_basis='RAW_VOLUME_SHARES_TIMES_CONDITIONAL_NOMINAL_CLOSE')
    return sample,json.dumps(data).encode()


class Tests(unittest.TestCase):
    def test_postsplit_price_return_and_liquidity_units(self):
        sample,raw=fixture();value=m.inspect(sample,raw,RECEIPT)
        self.assertEqual(value['return_count'],126);self.assertEqual(value['median_dollar_volume_usd'],'100000000')
        sample['numerical']['liquidity_rows'][-1]['dollar_volume']='2000000000'
        with self.assertRaises(ValueError):m.inspect(sample,raw,RECEIPT)

    def test_event_denominator_and_class_c_are_not_optional(self):
        for defect in ('delete','ratio','negative','bool','date','extra','class'):
            sample,raw=fixture();data=json.loads(raw);events=data['chart']['result'][0]['events']['splits'];event=events['1658151000']
            if defect=='delete':events.clear()
            if defect=='ratio':event['numerator']=10
            if defect=='negative':event.update(numerator=-20,denominator=-1)
            if defect=='bool':event['denominator']=True
            if defect=='date':event['date']+=86400
            if defect=='extra':events['another']=dict(event)
            if defect=='class':sample['official_specific_split_facts']['security_class']='CLASS_A_COMMON'
            with self.subTest(defect=defect),self.assertRaises(ValueError):m.inspect(sample,json.dumps(data).encode(),RECEIPT)

    def test_predecessor_and_disclosure_rejected(self):
        for defect in ('previous','sid','boolreturn','pit'):
            sample,raw=fixture();row=sample['numerical']['price_returns']['rows'][-1]
            if defect=='previous':row['previous_session']='2026-09-15'
            if defect=='sid':row['security_id']='GOOGL'
            if defect=='boolreturn':row['price_return']=False
            if defect=='pit':sample['point_in_time_verified']=True
            with self.subTest(defect=defect),self.assertRaises(ValueError):m.inspect(sample,raw,RECEIPT)


if __name__=='__main__':unittest.main()
