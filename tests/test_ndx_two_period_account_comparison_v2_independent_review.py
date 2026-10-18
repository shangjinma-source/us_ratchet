"""V2-only adversarial readback tests, no build or execution engine invocation."""
import copy
import math
import unittest
from scripts import ndx_two_period_account_comparison_20260919 as m
from test_ndx_two_period_account_comparison_20260919 import fixture


def receipt_fixture():
    candidate,target,price,identities,prefix=fixture()
    candidate['started_attempt']={'path':'synthetic.started','sha256':'a'*64}
    candidate['historical_expected_source_hashes']={'synthetic.source':'b'*64}
    raw=copy.deepcopy(candidate['execution'])
    for decision in raw['decisions']:
        for sid,target_row in decision['targets'].items():target_row['ticker']=candidate['internal_columns'][sid]
    receipt=dict(schema='TWO_PERIOD_RAW_EXECUTION_RECEIPT_V2',execution=raw,
        original_schedule=copy.deepcopy(candidate['schedule']),calendar=copy.deepcopy(candidate['calendar']),
        execution_contract=copy.deepcopy(candidate['execution_contract']),internal_columns=copy.deepcopy(candidate['internal_columns']),
        started_attempt=copy.deepcopy(candidate['started_attempt']),historical_expected_source_hashes=copy.deepcopy(candidate['historical_expected_source_hashes']),
        independent_accounting_completed=False,point_in_time_verified=False,promotion_allowed=False)
    return candidate,receipt,identities


class V2Review(unittest.TestCase):
    def test_v1_and_one_ulp_normalization_drift_rejected(self):
        for defect in ('v1','weight','evidence','count'):
            c,t,p,i,_=fixture()
            if defect=='v1':c['schema']='TWO_PERIOD_CONDITIONAL_FROZEN_ACCOUNT_V1'
            if defect=='weight':
                row=next(iter(c['normalized_schedule'][0]['targets'].values()))
                row['target_weight']=math.nextafter(row['target_weight'],math.inf)
            if defect=='evidence':c['normalization_evidence']['periods'][0]['binary_float_weight_sum']=math.nextafter(c['normalization_evidence']['periods'][0]['binary_float_weight_sum'],math.inf)
            if defect=='count':c['normalization_evidence']['periods'][0]['normalization_count']=2
            with self.subTest(defect=defect),self.assertRaises(ValueError):m.audit_account(c,t,p,i)

    def test_raw_receipt_all_nonlabel_fields_remain_exact(self):
        c,r,i=receipt_fixture();m.audit_raw_receipt(c,r,i)
        for defect in ('v1','cash','status','attempt','sources','label','newfield'):
            c,r,i=receipt_fixture()
            if defect=='v1':r['schema']='TWO_PERIOD_RAW_EXECUTION_RECEIPT_V1'
            if defect=='cash':r['execution']['daily'][0]['cash_usd']=24999.999999999996
            if defect=='status':r['execution']['decisions'][0]['status']='REJECTED'
            if defect=='attempt':r['started_attempt']['sha256']='c'*64
            if defect=='sources':r['historical_expected_source_hashes']={}
            if defect=='label':next(iter(r['execution']['decisions'][0]['targets'].values()))['ticker']='AMAT'
            if defect=='newfield':r['execution']['daily'][0]['undisclosed_fee']=1
            with self.subTest(defect=defect),self.assertRaises(ValueError):m.audit_raw_receipt(c,r,i)

    def test_metric_bool_nonfinite_and_cashflow_claim_rejected(self):
        for bad in (True,float('nan'),float('inf'),0):
            values=[25000]*21;values[7]=bad
            with self.subTest(bad=bad),self.assertRaises(ValueError):m.metrics(values)
        for flag in ('additional_cash_flows_supported','continuous_identity_interval_verified','corporate_action_completeness_verified'):
            c,t,p,i,_=fixture();c[flag]=True
            with self.subTest(flag=flag),self.assertRaises(ValueError):m.audit_account(c,t,p,i)

if __name__=='__main__':unittest.main()
