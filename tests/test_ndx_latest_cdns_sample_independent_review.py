import json
import unittest
from scripts import ndx_latest_cdns_sample_independent_audit_20260919 as m
from test_ndx_latest_cdns_sample_independent_audit_20260919 import fixture, RECEIPT


class ReviewTests(unittest.TestCase):
    def test_interior_day_loss_and_first_return_metadata_cannot_pass(self):
        for defect in ('day','first','count','gap_host'):
            sample,raw=fixture();body=json.loads(raw)
            if defect=='day':
                data=body['chart']['result'][0];data['timestamp'].pop(-20)
                for key in ('close','volume'):data['indicators']['quote'][0][key].pop(-20)
            if defect=='first':sample['numerical']['price_returns']['first_session_has_no_previous_close_return']=False
            if defect=='count':sample['numerical']['price_returns']['input_price_row_count']=True
            if defect=='gap_host':sample['official_action_evidence_gap']['official_q4_host_delegation_independently_verified']=True
            with self.subTest(defect=defect),self.assertRaises(ValueError):m.inspect(sample,json.dumps(body).encode(),RECEIPT)

    def test_decimal_error_boolean_is_not_an_error_measure(self):
        sample,raw=fixture();sample['numerical']['independent_decimal_return_max_error']=False
        with self.assertRaises(ValueError):m.inspect(sample,raw,RECEIPT)


if __name__=='__main__':unittest.main()
