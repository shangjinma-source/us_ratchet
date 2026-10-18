import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from scripts.current_quantity_v2_annual_input_preflight import inspect


class PreflightTests(unittest.TestCase):
    def fixture(self, root):
        start = datetime(2025, 1, 1, 16, tzinfo=timezone.utc)
        dates = [(start+timedelta(days=i)).date().isoformat() for i in range(253)]
        raw = {'chart': {'error': None, 'result': [{
            'meta': dict(symbol='A', currency='USD', instrumentType='EQUITY',
                         exchangeTimezoneName='America/New_York', dataGranularity='1d'),
            'timestamp': [int((start+timedelta(days=i)).timestamp()) for i in range(253)],
            'indicators': {'quote': [dict(open=[10]*253, high=[11]*253,
                                        low=[9]*253, close=[10]*253, volume=[1]*253)]}}]}}
        def put(name, value):
            data=json.dumps(value).encode(); (root/name).write_bytes(data)
            return hashlib.sha256(data).hexdigest()
        rawhash=put('raw.json', raw)
        manifest=dict(training_dates=dates, decision_date=dates[-1], source_hashes={'raw.json':rawhash},
                      candidates=[dict(ticker='A', security_id='sid:A', status='READY', training_source='raw.json')])
        return dict(root=root, year=2025, manifest_path='manifest.json',
                    manifest_sha256=put('manifest.json',manifest), calendar_path='calendar.json',
                    calendar_sha256=put('calendar.json',dict(session_dates=dates+['2025-12-31'])),
                    as_of='2026-01-01')

    def test_daily_full_training_never_proves_intraday_or_year(self):
        with tempfile.TemporaryDirectory() as temp:
            args=self.fixture(Path(temp)); result=inspect(**args)
            self.assertEqual(result['training_rows'][0]['training_present'],253)
            self.assertEqual(result['training_rows'][0]['supplied_year_sessions_missing'],['2025-12-31'])
            self.assertFalse(result['current_intraday_strategy_reproducible'])
            self.assertFalse(result['membership_full_year_verified'])
            self.assertEqual(result['search_calls'],0)

    def test_changed_bytes_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            args=self.fixture(Path(temp)); (Path(temp)/'raw.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'SOURCE_HASH_MISMATCH'):
                inspect(**args)

    def test_year_incomplete_and_path_escape(self):
        with tempfile.TemporaryDirectory() as temp:
            args=self.fixture(Path(temp)); args['as_of']='2025-10-15'
            self.assertFalse(inspect(**args)['year_completed'])
            args['manifest_path']='../outside.json'
            with self.assertRaisesRegex(ValueError,'SOURCE_OUTSIDE_ROOT'):
                inspect(**args)

    def test_capture_next_day_does_not_change_minute_date(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); args=self.fixture(root)
            folder=root/'observations'; (folder/'events').mkdir(parents=True)
            raw=json.dumps({'chart':{'result':[{'meta':dict(symbol='A',dataGranularity='1m',exchangeTimezoneName='America/New_York'),
                'timestamp':[int(datetime(2025,7,1,16,tzinfo=timezone.utc).timestamp())]}]}}).encode()
            (folder/'raw.bin').write_bytes(raw)
            event=dict(research_binding={'method':'OLD_TOP1'},response={'status':'UNAVAILABLE'},captures=[dict(ticker='A',captured_at='2025-07-02T16:00:00+00:00',path='raw.bin',sha256=hashlib.sha256(raw).hexdigest())])
            (folder/'events'/'one.json').write_text(json.dumps(event))
            result=inspect(**args,observation_directory='observations')
            self.assertEqual(result['minute_observation_days'],['2025-07-01'])
            self.assertEqual(result['minute_capture_dates'],['2025-07-02'])
            self.assertEqual(result['observation_method_counts'],{'OLD_TOP1':1})
            self.assertFalse(result['current_v2_usable_minute_coverage_verified'])


if __name__=='__main__': unittest.main()
