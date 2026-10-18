from copy import deepcopy
from datetime import datetime
import json
import unittest
from scripts import ndx_current_tsm_conditional_quote_20260919 as m


def fixture():
    dates=['2026-09-16','2026-09-17','2026-09-18'];times=[int(datetime.fromisoformat(d+'T13:30:00+00:00').timestamp()) for d in dates]
    end=int(datetime.fromisoformat('2026-09-19T11:00:00+00:00').timestamp())
    body=dict(chart=dict(error=None,result=[dict(meta=dict(symbol='TSM',currency='USD',exchangeTimezoneName='America/New_York',instrumentType='EQUITY',dataGranularity='1d'),
        timestamp=times,indicators=dict(quote=[dict(open=[100.25,101.5,102.],close=[101.,102.,103.])]),events=dict(dividends={str(times[0]):dict(date=times[0],amount=2.)}))]))
    receipt=dict(request_method='GET',credentials_sent=False,request_url=f'https://query1.finance.yahoo.com/v8/finance/chart/TSM?period1=1640995200&period2={end}&interval=1d&events=div,splits',received_at_utc='2026-09-19T11:00:01+00:00')
    return body,receipt,dates[:2]


class Tests(unittest.TestCase):
    def test_original_nominal_core_full_target_and_independent_decimal(self):
        body,receipt,calendar=fixture();result,audit=m.reconstruct(json.dumps(body).encode(),receipt,calendar)
        self.assertEqual(result['row_count'],2);self.assertEqual(audit['cells_checked'],4)
        self.assertEqual(m.Decimal(audit['maximum_absolute_decimal_error']),0)
        self.assertEqual([r['nominal_open'] for r in result['rows']],[100.25,101.5])
        self.assertFalse(result['dividends_applied_to_quote'])

    def test_calendar_upgrade_missing_and_new_split_reject(self):
        for defect in ('upgrade','missing','split','receipt'):
            body,receipt,calendar=fixture()
            if defect=='upgrade':calendar.append('2026-09-18')
            if defect=='missing':calendar.pop(0)
            if defect=='receipt':receipt['received_at_utc']='2026-09-17T11:00:00+00:00'
            if defect=='split':
                t=body['chart']['result'][0]['timestamp'][1]
                body['chart']['result'][0]['events']['splits']={str(t):dict(date=t,numerator=2,denominator=1,splitRatio='2:1')}
            with self.subTest(defect=defect),self.assertRaises(ValueError):m.reconstruct(json.dumps(body).encode(),receipt,calendar)

    def test_independent_bool_factor_and_corrupted_price_reject(self):
        body,receipt,calendar=fixture();raw=json.dumps(body).encode();result,_=m.reconstruct(raw,receipt,calendar)
        for defect in ('factor','price','nan'):
            changed=deepcopy(result)
            if defect=='factor':changed['rows'][0]['split_factor']=True
            if defect=='price':changed['rows'][0]['nominal_close']+=1
            if defect=='nan':changed['rows'][0]['nominal_close']=float('nan')
            with self.subTest(defect=defect),self.assertRaises(ValueError):m.decimal_audit(raw,changed,calendar)


if __name__=='__main__':unittest.main()
