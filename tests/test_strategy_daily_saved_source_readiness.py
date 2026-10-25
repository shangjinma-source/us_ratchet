import json
import unittest
from datetime import datetime, timedelta, timezone
from hashlib import sha256

from data.strategy_daily_saved_source_readiness import inspect_saved_daily_source


class SavedReadinessTests(unittest.TestCase):
    def fixture(self):
        # Synthetic calendar explicitly remains a test fixture.
        start=datetime(2026,1,1,21,tzinfo=timezone.utc)
        days=[start+timedelta(days=i) for i in range(20)]
        raw=json.dumps(dict(chart=dict(result=[dict(meta=dict(symbol='S',currency='USD'),
            timestamp=[int(d.timestamp()) for d in days],
            indicators=dict(quote=[dict(close=[100]*20)]))]))).encode()
        return dict(raw_bytes=raw,raw_sha256=sha256(raw).hexdigest(),
            captured_at='2026-01-20T22:00:00+00:00',ticker='S',signal_date='2026-01-20',
            calendar_sessions=[dict(date=d.date().isoformat(),close=d.isoformat()) for d in days],
            unit_review=dict(schema='REVIEWED_CONSTANT_DECISION_SHARE_UNITS_V1',
                unit_asof='2026-01-20',currency='USD',basis_id='test',review_reference='test'),
            permitted_for_strategy=True)

    def test_ready_means_review_only_and_never_approval(self):
        result=inspect_saved_daily_source(**self.fixture())
        self.assertEqual(result['reasons'],[])
        self.assertIsNone(result['normalized_inputs'])
        self.assertIsNone(result['approval_receipt'])

    def test_intraday_short_calendar_display_and_current_unit_review_wait(self):
        args=self.fixture();args.update(captured_at='2026-01-20T18:00:00+00:00',
            calendar_sessions=args['calendar_sessions'][-5:],permitted_for_strategy=False,
            unit_review=dict(schema='STRATEGY_TARGET_UNIT_REVIEW_V1'))
        self.assertEqual(set(inspect_saved_daily_source(**args)['reasons']),{
            'WAIT_STRATEGY_SOURCE_REVIEW','WAIT_TWENTY_SESSION_CALENDAR',
            'WAIT_AFTER_SESSION_CLOSE_CAPTURE','WAIT_HISTORICAL_UNIT_NORMALIZATION'})

    def test_missing_last_close_and_byte_tamper(self):
        args=self.fixture();data=json.loads(args['raw_bytes'])
        data['chart']['result'][0]['indicators']['quote'][0]['close'][-1]=None
        args['raw_bytes']=json.dumps(data).encode();args['raw_sha256']=sha256(args['raw_bytes']).hexdigest()
        self.assertIn('WAIT_COMPLETED_DAILY_PRICES',inspect_saved_daily_source(**args)['reasons'])
        args['raw_bytes']+=b' '
        with self.assertRaises(ValueError):inspect_saved_daily_source(**args)


if __name__=='__main__':
    unittest.main()
