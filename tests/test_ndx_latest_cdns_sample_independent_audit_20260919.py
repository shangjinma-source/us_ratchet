import json
import unittest
from test_ndx_latest_avgo_sample_independent_audit_20260919 import fixture as original,RECEIPT
from scripts import ndx_latest_cdns_sample_independent_audit_20260919 as m


def fixture():
    sample,raw=original()
    sample=json.loads(json.dumps(sample).replace('AVGO','CDNS').replace('0001730168','0000813672').replace('11135F101','127387108'))
    data=json.loads(raw.replace(b'AVGO',b'CDNS'))
    data['chart']['result'][0]['events']['splits']={}
    sample['returned_raw_events']=data['chart']['result'][0]['events']
    sample['numerical'].pop('observed_historical_split')
    sample.pop('official_specific_split_facts')
    sample.update(action_evidence_scope='ONLY_RETURNED_RAW_EVENTS_CONDITIONAL_RATIO_ONE',
                  gap_explanation='NO_COMPLETE_LOCAL_OFFICIAL_ACTION_HISTORY; NO_RETURNED_SPLITS_DOES_NOT_PROVE_NO_ACTIONS',
                  official_action_evidence_gap=json.loads(m.GAP.read_bytes()),
                  official_action_table_verified=False,record_date_used_as_ex_date=False,execution_authorized=False)
    return sample,json.dumps(data).encode()


class Tests(unittest.TestCase):
    def test_independent_126_returns_and_63_dollar_volume(self):
        sample,raw=fixture();result=m.inspect(sample,raw,RECEIPT)
        self.assertEqual(result['return_count'],126)
        self.assertEqual(result['liquidity_count'],63)
        self.assertEqual(result['median_dollar_volume_usd'],'100000000')

    def test_cannot_upgrade_refused_official_action_or_nested_permissions(self):
        for defect in ('status','complete','unit','nested','receipt','ratio'):
            sample,raw=fixture()
            if defect=='status':sample['official_action_evidence_gap']['probes'][0]['http_status']=200
            if defect=='complete':sample['official_action_table_verified']=True
            if defect=='unit':sample['numerical']['liquidity_legality_or_corporate_action_unit_independently_certified']=True
            if defect=='nested':sample['numerical']['price_returns']['execution_price_use_authorized']=True
            if defect=='receipt':sample['receipt_day_excluded']='2026-09-19'
            if defect=='ratio':sample['numerical']['input_payload']['daily_share_ratios'][0]['new_shares']=True
            with self.subTest(defect=defect),self.assertRaises(ValueError):m.inspect(sample,raw,RECEIPT)

    def test_raw_event_and_arithmetic_mutations_rejected(self):
        for defect in ('split','unknown','return','volume','predecessor','negative'):
            sample,raw=fixture();data=json.loads(raw)
            if defect=='split':data['chart']['result'][0]['events']['splits']={'x':{'numerator':2,'denominator':1}}
            if defect=='unknown':data['chart']['result'][0]['events']['capitalGains']={}
            if defect=='return':sample['numerical']['price_returns']['rows'][0]['price_return']=.1
            if defect=='volume':sample['numerical']['liquidity_rows'][0]['volume_shares']*=10
            if defect=='predecessor':sample['numerical']['price_returns']['rows'][0]['previous_session']='2026-01-01'
            if defect=='negative':data['chart']['result'][0]['indicators']['quote'][0]['close'][-2]=-100
            with self.subTest(defect=defect),self.assertRaises(ValueError):m.inspect(sample,json.dumps(data).encode(),RECEIPT)


if __name__=='__main__':unittest.main()
