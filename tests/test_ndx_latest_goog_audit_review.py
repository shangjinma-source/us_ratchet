from copy import deepcopy
import json
import unittest

from test_ndx_latest_goog_sample_independent_audit_20260919 import fixture, RECEIPT
from scripts import ndx_latest_goog_sample_independent_audit_20260919 as m


class Tests(unittest.TestCase):
    def test_unit_certification_and_event_witness_cannot_be_upgraded(self):
        for kind in ('unit','basis','event'):
            sample,raw=fixture();n=sample['numerical']
            if kind=='unit':n['liquidity_legality_or_corporate_action_unit_independently_certified']=True
            if kind=='basis':n['liquidity_basis']='TOTAL_RETURN_ADJCLOSE'
            if kind=='event':n['observed_historical_split']['new_shares']=40
            with self.subTest(kind=kind),self.assertRaises(ValueError):m.inspect(sample,raw,RECEIPT)

    def test_receipt_utc_ny_date_not_sample_claim(self):
        sample,raw=fixture();receipt=deepcopy(RECEIPT)
        receipt['received_at_utc']='2026-09-19T01:00:00+00:00'
        sample['received_at_utc']=receipt['received_at_utc']
        self.assertEqual(m.inspect(sample,raw,receipt)['return_end'],'2026-09-17')
        sample['receipt_day_excluded']='2026-09-19'
        receipt['completed_training_excludes_dates_on_or_after']='2026-09-19'
        with self.assertRaises(ValueError):m.inspect(sample,raw,receipt)

    def test_matching_negative_price_reconstruction_is_not_legal_numeric_price(self):
        sample,raw=fixture();body=json.loads(raw);n=sample['numerical']
        body['chart']['result'][0]['indicators']['quote'][0]['close']=[-100]*127
        for row in n['input_payload']['rows']:row['close']=-100
        for row in n['price_returns']['rows']:row.update(close=-100,previous_close=-100)
        for row in n['liquidity_rows']:row.update(nominal_close='-100',dollar_volume='-100000000')
        n['median_dollar_volume_usd']='-100000000';n['liquidity_numerical_threshold_passed']=False
        with self.assertRaises(ValueError):m.inspect(sample,json.dumps(body).encode(),RECEIPT)


if __name__=='__main__':unittest.main()
