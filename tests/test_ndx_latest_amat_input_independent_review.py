from copy import deepcopy
from datetime import datetime,timezone
import json
import unittest
import pandas as pd
from scripts import ndx_latest_amat_input_sample_20260919 as m


def fixture():
    days=[d.date().isoformat() for d in pd.bdate_range(end='2026-09-17',periods=506)]
    stamps=[int(datetime.fromisoformat(d+'T14:30:00+00:00').timestamp()) for d in days]
    closes=[100.]*506;closes[-1]=50.
    body=dict(chart=dict(result=[dict(meta=dict(symbol='AMAT',currency='USD'),timestamp=stamps,
        indicators=dict(quote=[dict(open=closes,close=closes,volume=[1000000]*506)]),events={})]))
    rows=[dict(session=d,ticker='AMAT',currency='USD',provider_timestamp=t,split_factor=1,split_factor_numerator='1',split_factor_denominator='1',later_split_effective_sessions=[],
        quote_open=c,quote_close=c,nominal_open=c,nominal_close=c) for d,t,c in zip(days,stamps,closes)]
    return dict(decoded=json.dumps(body).encode(),quote_rows=rows,reference=days[-505:],liquidity_threshold=50000000),body,days


class Tests(unittest.TestCase):
    def test_real_price_drop_not_inferred_split_and_dividend_not_total_return(self):
        args,body,days=fixture();result=m.calculate(**args)
        self.assertEqual(result['price_returns']['rows'][-1]['price_return'],-.5)
        self.assertEqual(len(result['price_returns']['rows']),126);self.assertEqual(len(result['liquidity_rows']),63)
        self.assertEqual(result['median_dollar_volume_usd'],'100000000.0')
        body['chart']['result'][0]['events']['dividends']={'unmodelled_cash':{'amount':20}}
        changed=m.calculate(**dict(args,decoded=json.dumps(body).encode()))
        self.assertEqual(result['price_returns'],changed['price_returns'])

    def test_missing_interior_raw_session_cannot_be_mislabeled_daily_return(self):
        args,body,days=fixture();args['reference'].pop(-20);args['reference'].insert(0,days[0])
        with self.assertRaises(ValueError):m.calculate(**args)

    def test_volume_units_and_factor_must_be_explicit(self):
        for defect in ('bool_volume','zero_volume','factor','split'):
            args,body,days=fixture()
            if defect=='bool_volume':body['chart']['result'][0]['indicators']['quote'][0]['volume'][-1]=True
            if defect=='zero_volume':body['chart']['result'][0]['indicators']['quote'][0]['volume'][-1]=0
            if defect=='factor':args['quote_rows'][-1]['split_factor']=2
            if defect=='split':body['chart']['result'][0]['events']['splits']={'event':{'numerator':2,'denominator':1}}
            args['decoded']=json.dumps(body).encode()
            with self.subTest(defect=defect),self.assertRaises(ValueError):m.calculate(**args)


if __name__=='__main__':unittest.main()
