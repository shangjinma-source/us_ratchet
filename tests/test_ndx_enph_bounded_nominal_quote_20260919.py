import json,hashlib
import unittest
from datetime import datetime
from scripts import ndx_enph_bounded_nominal_quote_20260919 as m


def fixture():
    calendar=[d for d in json.loads(m.CALENDAR.read_bytes())['calendar'] if m.START<=d<=m.END]
    times=[int(datetime.fromisoformat(d+'T13:30:00+00:00').timestamp()) for d in calendar]
    data=dict(chart=dict(error=None,result=[dict(meta=dict(symbol='ENPH',currency='USD',exchangeTimezoneName='America/New_York',instrumentType='EQUITY'),timestamp=times,indicators=dict(quote=[dict(open=[100.5]*21,close=[101.25]*21)]),events={})]))
    metadata=json.loads(m.META.read_bytes())
    return data,metadata,calendar


def run(data,metadata,calendar):
    raw=json.dumps(data).encode();metadata=dict(metadata,response_sha256=hashlib.sha256(raw).hexdigest(),response_bytes=len(raw))
    return m.calculate(raw,metadata,calendar)


class Tests(unittest.TestCase):
    def test_bounded21_same_raw_units_and_new_york_dates(self):
        result=run(*fixture());self.assertEqual(result['row_count'],21);self.assertEqual(result['decimal_open_close_count'],42)
        self.assertEqual(result['rows'][0]['session'],'2023-03-31');self.assertEqual(result['rows'][-1]['session'],'2023-05-01')
        self.assertEqual(result['rows'][0]['nominal_open'],100.5);self.assertEqual(result['maximum_decimal_serialization_error'],'0')

    def test_missing_duplicate_null_boolean_split_reject(self):
        for defect in ('missing','duplicate','null','bool','split','timezone','date'):
            data,metadata,calendar=fixture();r=data['chart']['result'][0]
            if defect=='missing':r['timestamp'].pop(5)
            if defect=='duplicate':r['timestamp'][5]=r['timestamp'][4]
            if defect=='null':r['indicators']['quote'][0]['close'][5]=None
            if defect=='bool':r['indicators']['quote'][0]['open'][5]=True
            if defect=='split':r['events']['splits']={'future':{}}
            if defect=='timezone':r['meta']['exchangeTimezoneName']='UTC'
            if defect=='date':r['timestamp'][0]-=14*3600
            with self.subTest(defect=defect),self.assertRaises(ValueError):run(data,metadata,calendar)

    def test_request_horizon_and_whole_events_retained(self):
        data,metadata,calendar=fixture();stamp=data['chart']['result'][0]['timestamp'][3]
        data['chart']['result'][0]['events']['dividends']={str(stamp):dict(date=stamp,amount=.25)}
        result=run(data,metadata,calendar);self.assertEqual(result['returned_events']['dividends'][str(stamp)]['amount'],.25)
        for defect in ('oldhorizon','blankduplicate','wrongticker'):
            data,metadata,calendar=fixture()
            if defect=='oldhorizon':metadata['request']['url']=metadata['request']['url'].replace('1789155251','1715000000')
            if defect=='blankduplicate':metadata['request']['url']+='&period2='
            if defect=='wrongticker':metadata['request']['url']=metadata['request']['url'].replace('/ENPH?','/OTHER?')
            with self.subTest(defect=defect),self.assertRaises(ValueError):run(data,metadata,calendar)


if __name__=='__main__':unittest.main()
