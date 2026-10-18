import json
import unittest

from test_ndx_latest_goog_input_sample_20260919 import fixture
from scripts import ndx_latest_goog_input_sample_20260919 as m


class Tests(unittest.TestCase):
    def test_split_share_counts_must_be_positive_finite(self):
        for n,d in ((-20,-1),(0,0),(20,0),(float('inf'),1),(float('nan'),1),(True,1)):
            args,body=fixture()
            event=body['chart']['result'][0]['events']['splits']['1658151000']
            event.update(numerator=n,denominator=d)
            with self.subTest(n=n,d=d),self.assertRaises(ValueError):
                m.calculate(**dict(args,decoded=json.dumps(body).encode()))

    def test_postsplit_volume_not_multiplied_and_dividend_excluded(self):
        args,body=fixture()
        result=m.calculate(**args)
        self.assertEqual(result['median_dollar_volume_usd'],'100000000.0')
        self.assertEqual(result['liquidity_rows'][-1]['dollar_volume'],'50000000.0')
        body['chart']['result'][0]['events']['dividends']={'fake_cash':{'amount':35}}
        changed=m.calculate(**dict(args,decoded=json.dumps(body).encode()))
        self.assertEqual(result['price_returns'],changed['price_returns'])
        args['quote_rows'][-1]['nominal_close'] *= 20
        args['quote_rows'][-1]['split_factor'] = 20
        with self.assertRaises(ValueError):m.calculate(**args)

    def test_skipped_observation_and_duplicate_event_rejected(self):
        args,body=fixture()
        args['reference'].pop(-20)
        args['reference'].insert(0,args['quote_rows'][0]['session'])
        with self.assertRaises(ValueError):m.calculate(**args)
        args,body=fixture()
        raw=args['decoded'].replace(b'"numerator": 20.0',b'"numerator": 20.0, "numerator": 20.0')
        self.assertNotEqual(raw,args['decoded'])
        with self.assertRaises(ValueError):m.calculate(**dict(args,decoded=raw))


if __name__=='__main__':unittest.main()
