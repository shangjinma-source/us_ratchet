import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from hashlib import sha256
from datetime import datetime,timezone
from data.roa_current_signal import CONTRACT_PATHS
from data.roa_daily_signal import RoaDailySignalProvider,states,load_completed_close_prices

ROOT=Path(__file__).resolve().parents[1]


class DailyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.now=datetime(2026,11,6,20,tzinfo=timezone.utc)
        self.calls=0
        def fetch():
            self.calls+=1
            return json.dumps({'chart':{'error':None,'result':[{'meta':{
                'symbol':'QQQ','currency':'USD','exchangeTimezoneName':'America/New_York','dataGranularity':'1d'},
                'timestamp':[1793975400],
                'indicators':{'quote':[{'open':[650],'high':[660],'low':[640],'close':[655],'volume':[10000]}]}}]}}).encode()
        self.provider=RoaDailySignalProvider(root=ROOT,path=Path(self.temp.name)/'state.json',
            expected_contract_hashes={p:sha256((ROOT/p).read_bytes()).hexdigest() for p in CONTRACT_PATHS},
            clock=lambda:self.now,fetch=fetch)
    def tearDown(self):self.temp.cleanup()

    def test_preclose_no_fetch_and_missing_next_session(self):
        self.assertEqual(self.provider()['signal_date'],'2026-11-05')
        self.assertEqual(self.provider.refresh_completed()['status'],'WAIT_COMPLETED_SESSION')
        self.assertEqual(self.calls,0)
        self.now=datetime(2026,11,9,14,tzinfo=timezone.utc)
        with self.assertRaisesRegex(ValueError,'WAIT_DAILY_MARKET_SIGNAL'):self.provider()

    def test_completed_update_and_recovery(self):
        self.now=datetime(2026,11,6,21,5,tzinfo=timezone.utc)
        self.assertEqual(self.provider.refresh_completed()['updated'],['2026-11-06'])
        self.now=datetime(2026,11,9,14,tzinfo=timezone.utc)
        result=self.provider()
        self.assertEqual(result['signal_date'],'2026-11-06')
        self.assertEqual(result['execution_not_before_session'],'2026-11-09')
        evidence=Path(result['daily_updates'][0]['raw_path']);evidence.write_bytes(b'bad')
        with self.assertRaisesRegex(ValueError,'DAILY_SOURCE_CHANGED'):self.provider()

    def test_new_month_refused(self):
        self.now=datetime(2026,12,1,14,tzinfo=timezone.utc)
        with self.assertRaisesRegex(ValueError,'WAIT_NEW_MONTH_SIGNAL'):self.provider()

    def test_real_ny_previous_evening_selects_next_session(self):
        self.now=datetime(2026,11,6,5,tzinfo=timezone.utc)
        result=self.provider()
        self.assertEqual(result['execution_not_before_session'],'2026-11-06')
        self.assertEqual(result['signal_date'],'2026-11-05')

    def test_exact_close_and_weekend_select_monday(self):
        self.now=datetime(2026,11,6,21,tzinfo=timezone.utc)
        self.provider.refresh_completed()
        self.assertEqual(self.provider()['execution_not_before_session'],'2026-11-09')
        self.now=datetime(2026,11,7,16,tzinfo=timezone.utc)
        self.assertEqual(self.provider()['execution_not_before_session'],'2026-11-09')

    def test_holiday_uses_calendar_not_weekday_guess(self):
        self.now=datetime(2026,11,26,16,tzinfo=timezone.utc)
        with patch.object(self.provider,'_read',return_value=({'2026-11-25':'100'},[])), \
             patch('data.roa_daily_signal.states',return_value={'2026-11-25':True}):
            self.assertEqual(self.provider()['execution_not_before_session'],'2026-11-27')

    def test_two_confirmation_not_one(self):
        values={str(i).zfill(3):'100' for i in range(200)}
        values['200']='101';self.assertFalse(states(values)['200'])
        values['201']='102';self.assertTrue(states(values)['201'])

    def test_close_reader_completion_identity_and_split(self):
        args=dict(identity_map={'s':{'ticker':'QQQ'}},session='2026-11-06',now=self.now,
            session_reader=self.provider.calendar,evidence_dir=self.temp.name,fetch=lambda ticker:self.provider.fetch())
        with self.assertRaisesRegex(ValueError,'WAIT_COMPLETED_SESSION'):load_completed_close_prices(**args)
        args['now']=datetime(2026,11,6,21,5,tzinfo=timezone.utc)
        self.assertEqual(load_completed_close_prices(**args)['prices'],{'s':'655'})
        args['identity_map']={'s':{'ticker':'WRONG'}}
        with self.assertRaisesRegex(ValueError,'DAILY_IDENTITY_INVALID'):load_completed_close_prices(**args)
        args['identity_map']={'s':{'ticker':'QQQ'}}
        raw=json.loads(self.provider.fetch());raw['chart']['result'][0]['events']={'splits':{'x':{'date':1793975400}}}
        args['fetch']=lambda ticker:json.dumps(raw).encode()
        with self.assertRaisesRegex(ValueError,'WAIT_CORPORATE_ACTION_CLOSE_ADMISSION'):load_completed_close_prices(**args)


if __name__=='__main__':unittest.main()
