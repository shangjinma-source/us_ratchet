import json
import unittest
from copy import deepcopy
from datetime import datetime,timedelta
from scripts import ndx_latest_amat_sample_independent_audit_20260919 as m


def fixture():
    days=[(datetime(2026,9,17)-timedelta(days=i)).date().isoformat() for i in reversed(range(127))]
    stamps=[int(datetime.fromisoformat(d+'T14:30:00+00:00').timestamp()) for d in days]
    raw=json.dumps(dict(chart=dict(result=[dict(meta=dict(symbol='AMAT',currency='USD'),timestamp=stamps,indicators=dict(quote=[dict(close=[100]*127,volume=[1000000]*127)]),events={})]))).encode()
    prices=[dict(security_id=m.SID,issuer_id=m.ISSUER,ticker='AMAT',session=d,close=100) for d in days]
    ratios=[dict(security_id=m.SID,session=d,new_shares=1,old_shares=1) for d in days]
    rows=[dict(security_id=m.SID,issuer_id=m.ISSUER,ticker='AMAT',previous_ticker='AMAT',session=d,previous_session=p,close=100,previous_close=100,price_return=0,declared_share_ratio='1',applied_share_ratio='1') for p,d in zip(days,days[1:])]
    n=dict(input_payload=dict(calendar=days,basis='NOMINAL_CLOSE',dividend_adjustment_in_close=False,securities={m.SID:{'issuer_id':m.ISSUER}},rows=prices,daily_share_ratios=ratios),price_returns=dict(rows=rows,calendar=days),liquidity_rows=[dict(session=d,volume_shares=1000000,nominal_close='100',dollar_volume='100000000') for d in days[-63:]],median_dollar_volume_usd='100000000',minimum_median_dollar_volume_usd='50000000',liquidity_numerical_threshold_passed=True)
    sample=dict(schema='LATEST_AMAT_RETROSPECTIVE_PRICE_RETURN_LIQUIDITY_SAMPLE_V1',cutoff=m.CUTOFF,security_id=m.SID,issuer_id=m.ISSUER,price_return_excludes_cash_dividends=True,ratio_one_is_explicit_research_condition=True,receipt_day_excluded='2026-09-18',numerical=n,**dict.fromkeys(m.FALSE,False))
    return sample,raw


class Tests(unittest.TestCase):
    def test_independent_constant_price_arithmetic(self):
        sample,raw=fixture();result=m.inspect(sample,raw)
        self.assertEqual(result['return_count'],126);self.assertEqual(result['liquidity_count'],63)
        self.assertEqual(result['maximum_return_error'],'0');self.assertEqual(result['median_dollar_volume_usd'],'100000000')

    def test_wrong_return_predecessor_volume_scope_rejected(self):
        for defect in ('return','predecessor','volume','scope','ratio','bool'):
            sample,raw=fixture();n=sample['numerical']
            if defect=='return':n['price_returns']['rows'][-1]['price_return']=.01
            if defect=='predecessor':n['price_returns']['rows'][-1]['previous_session']='2026-09-15'
            if defect=='volume':n['liquidity_rows'][-1]['dollar_volume']='999'
            if defect=='scope':sample['point_in_time_verified']=True
            if defect=='ratio':n['input_payload']['daily_share_ratios'][-1]['new_shares']=True
            if defect=='bool':n['price_returns']['rows'][-1]['price_return']=False
            with self.subTest(defect=defect),self.assertRaises(ValueError):m.inspect(sample,raw)


if __name__=='__main__':unittest.main()
