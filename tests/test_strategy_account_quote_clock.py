from datetime import datetime, timedelta
from hashlib import sha256
import json
import unittest
from data.strategy_account_quote_clock import wait_for_vendor_clock
from data.strategy_account_live_pullback_sources import candidate_from_yahoo_bytes
from test_current_quantity_v2_pullback_sources import payload, epoch
from test_strategy_account_unit_review import fixture
from data.strategy_account_unit_review import review_interval
from core.strategy_account_ledger import canonical


class QuoteClockTests(unittest.TestCase):
    def test_action_window_covers_last_even_when_after_capture(self):
        args=fixture();mark=args['marks']['S']
        mark['captured_at']='2026-10-16T13:59:59.500000+00:00'
        mark['checked_at']='2026-10-16T14:00:00+00:00'
        args['marks_sha256']=sha256(canonical(args['marks'])).hexdigest()
        self.assertEqual(review_interval(**args)['securities']['S']['covered_through'],mark['observed_at'])
        mark['observed_at']='2026-10-16T14:00:00.100000+00:00'
        mark['checked_at']=mark['observed_at'];args['now']='2026-10-16T14:00:01+00:00'
        args['marks_sha256']=sha256(canonical(args['marks'])).hexdigest()
        with self.assertRaisesRegex(ValueError,'ACTION_INTERVAL_NOT_COVERED'):review_interval(**args)

    def test_real_clock_gate_does_not_move_capture_and_times_out(self):
        captured=datetime.fromisoformat('2026-10-15T09:32:13.5-04:00')
        raw=json.dumps(payload()).encode();elapsed=[0.0]
        def sleep(seconds):elapsed[0]+=seconds
        checked=wait_for_vendor_clock(raw,captured_at=captured,
            clock=lambda:captured+timedelta(seconds=elapsed[0]),sleep=sleep,monotonic=lambda:elapsed[0])
        self.assertGreaterEqual(checked,captured+timedelta(seconds=.5))
        self.assertEqual(captured.microsecond,500000)
        elapsed[0]=0
        with self.assertRaisesRegex(ValueError,'VENDOR_CLOCK_WAIT_EXPIRED'):
            wait_for_vendor_clock(raw,captured_at=captured,clock=lambda:captured,
                sleep=sleep,monotonic=lambda:elapsed[0])
        with self.assertRaisesRegex(ValueError,'EXCEEDS_ONE_SECOND'):
            wait_for_vendor_clock(raw,captured_at=captured-timedelta(seconds=1),clock=lambda:captured)

    def run_parser(self, data, captured, checked):
        raw=json.dumps(data).encode()
        return candidate_from_yahoo_bytes(raw=raw,expected_sha256=sha256(raw).hexdigest(),
            security_id='SNDK-ID',ticker='SNDK',session='2026-10-15',
            session_open='2026-10-15T09:30:00-04:00',session_close='2026-10-15T16:00:00-04:00',
            captured_at='2026-10-15T'+captured+'-04:00',checked_at='2026-10-15T'+checked+'-04:00',
            now='2026-10-15T'+checked+'-04:00',rebound_fraction='1/2',minimum_discount='1/200',
            maximum_age_seconds=120,previous_cap=None)

    def test_wait_across_minute_never_promotes_partial_bar_or_snapshot(self):
        data=payload();entry=data['chart']['result'][0]
        entry['meta']['regularMarketTime']=epoch('09:33:00')
        entry['timestamp'].append(epoch('09:33:00'))
        for key in ('open','high','low','close'):entry['indicators']['quote'][0][key].append(1356.8)
        entry['indicators']['quote'][0]['volume'].append(0)
        result=self.run_parser(data,'09:32:59.5','09:33:00.1')
        self.assertEqual(len(result['reference']['bars']),2)
        self.assertEqual(result['receipt']['excluded_rows']['incomplete_tail'],1)
        self.assertEqual(result['receipt']['excluded_rows']['provider_last_trade_snapshot'],1)
        self.assertEqual(result['reference']['captured_at'],'2026-10-15T09:32:59.500000-04:00')
        with self.assertRaises(ValueError):self.run_parser(data,'09:32:59.5','09:32:59.9')
        with self.assertRaises(ValueError):self.run_parser(data,'09:32:58.9','09:33:00.1')

    def test_subsecond_snapshot_not_candle(self):
        data=payload();entry=data['chart']['result'][0]
        entry['timestamp'].append(epoch('09:32:14'))
        for key in ('open','high','low','close'):entry['indicators']['quote'][0][key].append(1356.8)
        entry['indicators']['quote'][0]['volume'].append(0)
        result=self.run_parser(data,'09:32:13.8','09:32:14.1')
        self.assertEqual(len(result['reference']['bars']),2)
        self.assertEqual(result['receipt']['excluded_rows']['provider_last_trade_snapshot'],1)


if __name__=='__main__':unittest.main()
