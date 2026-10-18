"""Independent synthetic event-boundary tests; no source IO or financial engine."""
import copy
import json
import unittest
from datetime import date, datetime, timedelta
from fractions import Fraction
from backtest import ndx_conditional_channel_input_research as m


def fixture(event_index=None,kind='ORDINARY_SPLIT'):
    days=[];d=date(2025,1,1)
    while len(days)<140:
        if d.weekday()<5:days.append(d.isoformat())
        d+=timedelta(days=1)
    times=[int(datetime.fromisoformat(day+'T14:30:00+00:00').timestamp()) for day in days]
    calendar=days[5:132];events={};policy=[]
    if event_index is not None:
        stamp=times[event_index]
        events={'splits':{str(stamp):dict(date=stamp,numerator=2,denominator=1,splitRatio='2:1')}}
        policy=[dict(session=days[event_index],numerator=2,denominator=1,kind=kind)]
    body=dict(chart=dict(error=None,result=[dict(meta=dict(symbol='TEST',currency='USD',instrumentType='EQUITY',exchangeTimezoneName='America/New_York',dataGranularity='1d'),
        timestamp=times,indicators={'quote':[dict(open=[100.]*140,close=[100.]*140,volume=[1000000]*140)]},events=events)]))
    rows=[]
    for day,stamp in zip(days,times):
        factor=2 if event_index is not None and kind=='ORDINARY_SPLIT' and day<days[event_index] else 1
        rows.append(dict(session=day,ticker='TEST',currency='USD',provider_timestamp=stamp,quote_open=100.,quote_close=100.,
            nominal_open=100.*factor,nominal_close=100.*factor,split_factor=factor,split_factor_numerator=str(factor),split_factor_denominator='1',
            later_split_effective_sessions=[days[event_index]] if factor==2 else []))
    args=dict(ticker='TEST',raw_bytes=json.dumps(body).encode(),quote_rows=rows,calendar=calendar,cutoff=calendar[-1],exclude_on_or_after=days[-1],event_policy=policy,
        regular_floor=calendar[0] if kind=='BEFORE_PARTITION_UNMODELLED' else None)
    return args,body,days


class ReviewTests(unittest.TestCase):
    def test_ordinary_split_neutral_returns_and_future_volume_block(self):
        for event_index in (90,135):
            args,_,days=fixture(event_index);result=m.build_channel_input(**args)
            self.assertEqual(len(result['price_returns']),126)
            self.assertTrue(all(r['price_return']==0 for r in result['price_returns']))
            self.assertEqual(result['liquidity']['status'],'BLOCKED_VOLUME_UNIT_UNKNOWN')
            self.assertIsNone(result['liquidity']['rows'])
            self.assertEqual(result['coordinate_kind'],'PROVIDER_TICKER_CHANNEL_NOT_SECURITY_ID')
            self.assertFalse(result['security_identity_verified'])

    def test_partition_event_retained_and_window_unmodelled_rejected(self):
        args,_,_=fixture(5,'BEFORE_PARTITION_UNMODELLED');result=m.build_channel_input(**args)
        self.assertTrue(result['returned_events']['splits'])
        self.assertTrue(all(r['price_return']==0 for r in result['price_returns']))
        self.assertEqual(result['liquidity']['status'],'CONDITIONAL_RAW_VOLUME_TIMES_NOMINAL_CLOSE')
        args,_,_=fixture(6,'BEFORE_PARTITION_UNMODELLED')
        with self.assertRaises(ValueError):m.build_channel_input(**args)
        args,_,_=fixture(5,'BEFORE_PARTITION_UNMODELLED');args['regular_floor']=None
        with self.assertRaises(ValueError):m.build_channel_input(**args)

    def test_events_must_not_be_omitted_or_complex_channel_silently_removed(self):
        args,body,_=fixture(2);args['event_policy']=[]
        with self.assertRaises(ValueError):m.build_channel_input(**args)
        args,body,_=fixture();body['chart']['result'][0]['events']['spinoff']={};args['raw_bytes']=json.dumps(body).encode()
        with self.assertRaises(ValueError):m.build_channel_input(**args)

    def test_split_ratio_text_must_be_positive_explicit_pair(self):
        for ratio in ('2','-2:-1','2/1'):
            args,body,_=fixture(90);next(iter(body['chart']['result'][0]['events']['splits'].values()))['splitRatio']=ratio
            args['raw_bytes']=json.dumps(body).encode()
            with self.subTest(ratio=ratio),self.assertRaises(ValueError):m.build_channel_input(**args)

    def test_no_compressed_calendar_or_boolean_volume(self):
        args,body,_=fixture();args['quote_rows'].pop(90)
        with self.assertRaises(ValueError):m.build_channel_input(**args)
        args,body,days=fixture();args['calendar'].pop(90);args['calendar'].insert(0,days[4])
        with self.assertRaises(ValueError):m.build_channel_input(**args)
        args,body,_=fixture();body['chart']['result'][0]['indicators']['quote'][0]['volume'][130]=True;args['raw_bytes']=json.dumps(body).encode()
        with self.assertRaises(ValueError):m.build_channel_input(**args)


if __name__=='__main__':unittest.main()
