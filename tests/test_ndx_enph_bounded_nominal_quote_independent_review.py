from datetime import datetime
import hashlib
import json
import unittest
from scripts import ndx_enph_bounded_nominal_quote_20260919 as m
from test_ndx_enph_bounded_nominal_quote_20260919 import fixture,run


class Tests(unittest.TestCase):
    def test_after_window_split_still_blocks_factor_one(self):
        data,metadata,calendar=fixture();stamp=int(datetime.fromisoformat('2024-07-15T13:30:00+00:00').timestamp())
        data['chart']['result'][0]['events']['splits']={str(stamp):dict(date=stamp,numerator=2,denominator=1,splitRatio='2:1')}
        with self.assertRaises(ValueError):run(data,metadata,calendar)

    def test_large_dividend_retained_but_never_deducted_from_quotes(self):
        data,metadata,calendar=fixture();stamp=data['chart']['result'][0]['timestamp'][3]
        data['chart']['result'][0]['events']['dividends']={str(stamp):dict(date=stamp,amount=999.)}
        result=run(data,metadata,calendar)
        self.assertEqual(result['returned_events']['dividends'][str(stamp)]['amount'],999.)
        self.assertTrue(all(r['nominal_open']==100.5 and r['nominal_close']==101.25 for r in result['rows']))

    def test_wrong_raw_binding_and_compressed_calendar_rejected(self):
        data,metadata,calendar=fixture();raw=json.dumps(data).encode()
        metadata=dict(metadata,response_sha256='0'*64,response_bytes=len(raw))
        with self.assertRaises(ValueError):m.calculate(raw,metadata,calendar)
        data,metadata,calendar=fixture();calendar.pop(7)
        with self.assertRaises(ValueError):run(data,metadata,calendar)


if __name__=='__main__':unittest.main()
