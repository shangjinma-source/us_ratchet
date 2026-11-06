import json
from datetime import datetime,timezone
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
from data.roa_monthly_loader import RoaMonthlySelectionLoader
from scripts.research.prepare_roa_monthly_package import prepare


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.root=Path(self.tmp.name)
        def save(name,obj):
            path=self.root/name;path.write_text(json.dumps(obj));return dict(path=name,sha256=sha256(path.read_bytes()).hexdigest())
        self.fact=save('facts.json',{'value':1})
        self.request=dict(manifest=save('manifest.json',{'decision_date':'2026-10-30'}),
            session_calendar=save('calendar.json',{'schema':'FIXED_EXCHANGE_SESSIONS_V1','sessions':[{'date':'2026-10-30','close':'2026-10-30T20:00:00+00:00'},{'date':'2026-11-02','close':'2026-11-02T21:00:00+00:00'}]}),
            training_calendar=save('training.json',{'schema':'VERIFIED_SCHEDULE_DATES_V1','sessions':[{'date':'2026-10-30'},{'date':'2026-11-02'}]}),
            expected_month='2026-11',output_directory='prepared')
        self.artifact=dict(schema='ROA_MONTH_SELECTION_V1',effective_month='2026-11',first_execution_session='2026-11-02',
            decision_date='2026-10-30',financial_cutoff='2026-09-30',selection={'selected':['A']},
            securities=[{'security_id':'A','ticker':'A'}],weights={'A':'1/10'},source_hashes={'facts.json':self.fact['sha256']},selection_id='preimage')
        self.now=datetime(2026,11,6,5,tzinfo=timezone.utc)
    def tearDown(self):self.tmp.cleanup()

    def test_full_preparation_freezes_data_but_does_not_register(self):
        with patch('scripts.research.prepare_roa_monthly_package.generate_month_selection',return_value=self.artifact):
            result=prepare(root=self.root,request=self.request,now=self.now,create=True)
        self.assertEqual(result['status'],'PREPARED_VERIFIED_NOT_REGISTERED')
        registry=json.loads((self.root/result['registry_proposal']).read_text())
        (self.root/'facts.json').write_text('{"value":999}')
        frozen=RoaMonthlySelectionLoader(root=self.root,registry=registry)('2026-11-02')
        self.assertEqual(frozen['weights'],{'A':'1/10'})
        self.assertFalse((self.root/'production.json').exists())
        self.assertFalse(result['account_writes']);self.assertFalse(result['schedules_changed'])

    def test_preclose_missing_and_wrong_requested_month_reject(self):
        with self.assertRaisesRegex(ValueError,'WAIT_COMPLETED_MONTH_END'):
            prepare(root=self.root,request=self.request,now=datetime(2026,10,30,19,tzinfo=timezone.utc))
        with patch('scripts.research.prepare_roa_monthly_package.generate_month_selection',return_value=self.artifact):
            with self.assertRaisesRegex(ValueError,'WAIT_REQUESTED_MONTH_INPUTS'):
                prepare(root=self.root,request=dict(self.request,expected_month='2026-12'),now=self.now)
        (self.root/'manifest.json').unlink()
        with self.assertRaisesRegex(ValueError,'WAIT_REQUIRED_MONTH_INPUT'):
            prepare(root=self.root,request=self.request,now=self.now)

    def test_dry_run_writes_nothing(self):
        with patch('scripts.research.prepare_roa_monthly_package.generate_month_selection',return_value=self.artifact):
            result=prepare(root=self.root,request=self.request,now=self.now)
        self.assertEqual(result['status'],'DRY_RUN_READY_NOT_REGISTERED')
        self.assertFalse((self.root/'prepared').exists())

    def test_calendar_disagreement_rejected_before_generation(self):
        path=self.root/'calendar.json';calendar=json.loads(path.read_text())
        calendar['sessions'][1]['date']='2026-11-03';path.write_text(json.dumps(calendar))
        self.request['session_calendar']['sha256']=sha256(path.read_bytes()).hexdigest()
        with patch('scripts.research.prepare_roa_monthly_package.generate_month_selection') as generate:
            with self.assertRaisesRegex(ValueError,'MONTH_CALENDARS_NEXT_SESSION_CONFLICT'):
                prepare(root=self.root,request=self.request,now=self.now)
            generate.assert_not_called()
        calendar['sessions']=calendar['sessions'][:1];path.write_text(json.dumps(calendar))
        self.request['session_calendar']['sha256']=sha256(path.read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError,'WAIT_NEXT_SESSION_CALENDAR'):
            prepare(root=self.root,request=self.request,now=self.now)


if __name__=='__main__':unittest.main()
