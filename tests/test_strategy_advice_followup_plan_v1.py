import unittest,tempfile,json
from datetime import datetime,timedelta,timezone
from pathlib import Path
from hashlib import sha256
from data.strategy_daily_advice_journal_v1 import encoded
from data.strategy_advice_followup_plan_v1 import plan_journal_page, reconcile_observation_plan
import test_daily_advice_journal_v1 as fixture


class FollowupPlanTests(unittest.TestCase):
    def setup_case(self,folder):
        wrapper,journal,clock,response=fixture.AdviceTests().setup_case(folder)
        response['reference_quotes']['A'].update(security_id='A',ticker='AAA')
        wrapper.policy_references={'policy_id':'TEST_POLICY','evidence_references':{'trusted_release_sha256':'a'*64}}
        result=wrapper.preview(expected_revision='revision',target_id='target')
        self.assertEqual(result['observation_record']['status'],'SAVED')
        dates=[];day=clock[0].date()
        for offset in range(40):
            value=day+timedelta(days=offset)
            if value.weekday()<5:
                # Explicit synthetic calendar; no assertion of official schedules.
                dates.append({'date':value.isoformat(),'open':value.isoformat()+'T13:30:00+00:00','close':value.isoformat()+'T20:00:00+00:00'})
        raw=encoded({'schema':'FIXED_EXCHANGE_SESSIONS_V1','exchange':'NASDAQ','sessions':dates})
        def plan(now,**kwargs):
            return plan_journal_page(journal=journal,account_id='account',calendar_bytes=raw,
                calendar_sha256=sha256(raw).hexdigest(),now=now,**kwargs)
        return wrapper,journal,clock,response,raw,plan

    def test_due_sessions_deterministic_readonly(self):
        with tempfile.TemporaryDirectory() as folder:
            wrapper,journal,clock,response,raw,plan=self.setup_case(folder)
            before=journal.path.read_bytes()
            first=plan(clock[0])['items'][0]['observations']
            self.assertEqual([x['horizon_sessions'] for x in first],[1,5,20])
            self.assertEqual([x['status'] for x in first],['WAIT_CLOSE']*3)
            after=plan(datetime.fromisoformat(first[0]['observation_close']))['items'][0]['observations']
            self.assertEqual(after[0]['status'],'DUE')
            self.assertEqual(after[0]['observation_id'],first[0]['observation_id'])
            self.assertFalse(after[0]['capture_admitted']);self.assertFalse(after[0]['actual_fill_inferred'])
            self.assertEqual(journal.path.read_bytes(),before)
            event=journal.page(account_id='account')['items'][0]['event_id']
            journal.record_return(event,dict(status='READY',checked_at=clock[0].isoformat()))
            self.assertEqual(plan(clock[0])['items'][0]['observations'][0]['observation_id'],first[0]['observation_id'])
            self.assertEqual(plan(clock[0],after=1)['items'],[])

    def test_wait_return_and_no_orders_excluded(self):
        with tempfile.TemporaryDirectory() as folder:
            wrapper,journal,clock,response,raw,plan=self.setup_case(folder)
            page=journal.page(account_id='account');event=page['items'][0]['event_id']
            journal.record_return(event,dict(status='WAIT',checked_at=clock[0].isoformat()))
            self.assertEqual(plan(clock[0])['items'][0]['status'],'NO_ACTIONABLE_ADVICE')
            response.update(status='HOLD',new_orders=[],reference_quotes={})
            wrapper.preview(expected_revision='revision',target_id='target')
            self.assertTrue(all(not x['observations'] for x in plan(clock[0])['items']))

    def test_calendar_tamper_future_and_missing_horizon(self):
        with tempfile.TemporaryDirectory() as folder:
            wrapper,journal,clock,response,raw,plan=self.setup_case(folder)
            with self.assertRaisesRegex(ValueError,'HASH'):
                plan_journal_page(journal=journal,account_id='account',calendar_bytes=raw+b' ',calendar_sha256=sha256(raw).hexdigest(),now=clock[0])
            with self.assertRaises(ValueError):plan(clock[0]-timedelta(seconds=1))
            calendar=json.loads(raw);calendar['sessions']=calendar['sessions'][:2];short=encoded(calendar)
            result=plan_journal_page(journal=journal,account_id='account',calendar_bytes=short,calendar_sha256=sha256(short).hexdigest(),now=clock[0])
            self.assertEqual([x['status'] for x in result['items'][0]['observations']],['WAIT_CLOSE','WAIT_CALENDAR','WAIT_CALENDAR'])

    def test_calendar_extension_keeps_id_and_changed_due_date_conflicts(self):
        with tempfile.TemporaryDirectory() as folder:
            wrapper,journal,clock,response,raw,plan=self.setup_case(folder)
            complete=json.loads(raw)
            partial=dict(complete,sessions=complete['sessions'][:2])
            def evaluate(calendar):
                data=encoded(calendar)
                return plan_journal_page(journal=journal,account_id='account',calendar_bytes=data,
                    calendar_sha256=sha256(data).hexdigest(),now=clock[0])
            short=evaluate(partial);full=evaluate(complete)
            self.assertEqual(short['cursor_semantics'],'SCAN_ONLY_NOT_COMPLETION')
            self.assertTrue(short['future_recheck_required'])
            old=short['items'][0]['observations'];new=full['items'][0]['observations']
            self.assertEqual([row['observation_id'] for row in old],[row['observation_id'] for row in new])
            self.assertNotEqual(old[0]['calendar_sha256'],new[0]['calendar_sha256'])
            self.assertEqual(reconcile_observation_plan(old[0],new[0]),new[0])
            self.assertEqual(reconcile_observation_plan(old[1],new[1]),new[1])
            changed=dict(complete,sessions=[complete['sessions'][0]]+complete['sessions'][2:])
            shifted=evaluate(changed)['items'][0]['observations'][0]
            self.assertEqual(old[0]['observation_id'],shifted['observation_id'])
            with self.assertRaisesRegex(ValueError,'CALENDAR_CONFLICT'):
                reconcile_observation_plan(old[0],shifted)

    def test_sell_keeps_price_baseline_not_profit(self):
        with tempfile.TemporaryDirectory() as folder:
            wrapper,journal,clock,response,raw,plan=self.setup_case(folder)
            response['new_orders'][0]['side']='SELL'
            wrapper.preview(expected_revision='revision',target_id='target')
            rows=plan(clock[0])['items'][1]['observations']
            self.assertEqual(rows[0]['side'],'SELL');self.assertEqual(rows[0]['reference_limit'],'10')
            self.assertFalse(rows[0]['performance_computed'])

if __name__=='__main__':unittest.main()
