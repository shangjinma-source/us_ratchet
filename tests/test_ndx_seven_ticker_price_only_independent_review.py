import unittest
from test_ndx_seven_ticker_price_only_20260919 import fixture,change_raw
from scripts import ndx_seven_ticker_price_only_20260919 as m


class Tests(unittest.TestCase):
    def test_historical_split_cannot_disappear_even_when_before_window(self):
        args=fixture('FTNT');change_raw(args,lambda d:d['events'].pop('splits'))
        with self.assertRaises(ValueError):m.inspect_channel(**args)

    def test_negative_or_extra_future_event_rejected(self):
        args=fixture('AVGO')
        change_raw(args,lambda d:next(iter(d['events']['splits'].values())).update(numerator=-10,denominator=-1))
        with self.assertRaises(ValueError):m.inspect_channel(**args)
        args=fixture('ADI')
        def extra(d):
            stamp=d['timestamp'][-2];d.setdefault('events',{})['splits']={str(stamp):dict(date=stamp,numerator=2,denominator=1,splitRatio='2:1')}
        change_raw(args,extra)
        with self.assertRaises(ValueError):m.inspect_channel(**args)

    def test_old_horizon_and_non_equity_rejected(self):
        args=fixture('ENPH');args['received_at_utc']='2026-09-18T19:34:11+00:00'
        with self.assertRaises(ValueError):m.inspect_channel(**args)
        args=fixture('BKR');change_raw(args,lambda d:d['meta'].update(instrumentType='ETF'))
        with self.assertRaises(ValueError):m.inspect_channel(**args)


if __name__=='__main__':unittest.main()
