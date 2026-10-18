import json
from copy import deepcopy
from datetime import datetime
import unittest
from scripts import ndx_post_action_four_independent_audit_20260919 as m


def sample():
    days=['2026-06-26','2026-06-29','2026-06-30','2026-07-01']
    stamps=[int(datetime.fromisoformat(d+'T13:30:00+00:00').timestamp()) for d in days]
    data=dict(meta=dict(symbol='HON'),timestamp=stamps,indicators=dict(quote=[dict(open=[100,90.25,91.5,92],close=[101,91.25,92.5,93])]))
    raw=json.dumps(dict(chart=dict(result=[data]))).encode()
    rows=[dict(ticker='HON',currency='USD',session=days[i],provider_timestamp=stamps[i],factor=1,factor_numerator='1',factor_denominator='1',
               returned_later_split_like_events=[],quote_open=data['indicators']['quote'][0]['open'][i],nominal_open=data['indicators']['quote'][0]['open'][i],
               quote_close=data['indicators']['quote'][0]['close'][i],nominal_close=data['indicators']['quote'][0]['close'][i]) for i in (1,2)]
    return raw,dict(rows=rows,row_count=2,received_at_utc='2026-07-01T18:00:00+00:00')


class Tests(unittest.TestCase):
    def test_factor_one_and_full_calendar(self):
        raw,result=sample();audit=m.audit_prices(raw,result,'HON')
        self.assertEqual(m.Decimal(audit['maximum_absolute_decimal_error']),m.Decimal(0));self.assertEqual(audit['cells_checked'],4)
    def test_bool_factor_missing_calendar_quote_corruption_and_nonfinite(self):
        for defect in ('factor','missing','quote','nan'):
            raw,result=sample()
            if defect=='factor':result['rows'][0]['factor']=True
            if defect=='missing':result['rows'].pop();result['row_count']=1
            if defect=='quote':result['rows'][0]['nominal_open']+=1
            if defect=='nan':result['rows'][0]['nominal_open']=float('nan')
            with self.subTest(defect=defect),self.assertRaises(ValueError):m.audit_prices(raw,result,'HON')


if __name__=='__main__':unittest.main()
