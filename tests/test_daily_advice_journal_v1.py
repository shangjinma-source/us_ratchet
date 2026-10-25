import unittest
import tempfile
from pathlib import Path
from datetime import datetime,timezone,timedelta
from copy import deepcopy
from types import SimpleNamespace
from fastapi import FastAPI
from fastapi.testclient import TestClient
from data.strategy_daily_advice_journal_v1 import DailyAdviceJournalV1
from data.strategy_observed_daily_admission_v1 import ObservedDailyAdmission
from api.strategy_advice_observations_v1 import create_router


class AdviceTests(unittest.TestCase):
    def setup_case(self, folder):
        now=datetime(2026,10,20,14,tzinfo=timezone.utc)
        state={'account_id':'account','revision':'revision'}
        target={'target_id':'target','payload':{'target_month':'2026-10'}}
        response={'status':'READY','account_revision':'revision','target_id':'target',
            'new_orders':[{'security_id':'A','side':'BUY','quantity':1,'limit_price':'10'}],
            'reference_quotes':{'A':{'observed_at':now.isoformat(),'reference_valid_until':(now+timedelta(seconds=120)).isoformat()}}}
        monthly=SimpleNamespace(accounts=SimpleNamespace(read=lambda:deepcopy(state)),current=lambda:deepcopy(target))
        clock=[now]
        journal=DailyAdviceJournalV1(Path(folder)/'audit.sqlite3',clock=lambda:clock[0])
        wrapper=ObservedDailyAdmission(service=SimpleNamespace(preview=lambda **kw:deepcopy(response)),monthly=monthly,
            journal=journal,clock=lambda:clock[0],validate_sources=lambda:None,policy_references={})
        return wrapper,journal,clock,response

    def test_creation_pagination_conflict_and_readonly_api(self):
        with tempfile.TemporaryDirectory() as folder:
            wrapper,journal,clock,response=self.setup_case(folder)
            result=wrapper.preview(expected_revision='revision',target_id='target')
            self.assertEqual(result['observation_record']['status'],'SAVED')
            with journal._connection(readonly=True) as db:
                import json
                event=json.loads(db.execute('SELECT body FROM advice_events').fetchone()[0])
            journal.append(event,now=clock[0])
            event['target_month']='2026-11'
            with self.assertRaisesRegex(ValueError,'CONFLICT'):journal.append(event,now=clock[0])
            app=FastAPI();app.include_router(create_router(journal=journal,account_id='account'))
            with TestClient(app) as client:
                page=client.get('/api/strategy-advice-v1/observations').json()
                self.assertEqual(len(page['items']),1)
                self.assertFalse(page['items'][0]['evidence_complete'])
                self.assertEqual(client.get('/api/strategy-advice-v1/observations?limit=101').status_code,422)
                self.assertEqual(client.post('/api/strategy-advice-v1/observations').status_code,405)
            self.assertEqual(journal.page(account_id='other')['items'],[])

    def test_expiry_during_write_preserves_candidate(self):
        with tempfile.TemporaryDirectory() as folder:
            wrapper,journal,clock,response=self.setup_case(folder)
            original=journal.append
            def slow(event,**kw):
                value=original(event,**kw);clock[0]+=timedelta(seconds=121);return value
            journal.append=slow
            result=wrapper.preview(expected_revision='revision',target_id='target')
            self.assertEqual(result['status'],'WAIT');self.assertEqual(result['new_orders'],[])
            item=journal.page(account_id='account')['items'][0]
            self.assertEqual((item['generated_status'],item['final_return_status']),('READY','WAIT'))

    def test_source_drift_future_quote_and_write_failure(self):
        for mode in ('source','future','write'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as folder:
                wrapper,journal,clock,response=self.setup_case(folder)
                if mode=='source':
                    count=[0]
                    def validate():
                        count[0]+=1
                        if count[0]>1:raise ValueError('SOURCE_CHANGED')
                    wrapper.validate_sources=validate
                if mode=='future':response['reference_quotes']['A']['observed_at']=(clock[0]+timedelta(seconds=1)).isoformat()
                if mode=='write':journal.append=lambda *a,**k:(_ for _ in ()).throw(OSError('disk full'))
                result=wrapper.preview(expected_revision='revision',target_id='target')
                if mode=='write':self.assertEqual(result['observation_record']['status'],'UNAVAILABLE')
                else:self.assertEqual(result['status'],'WAIT')

    def test_sql_account_and_return_tampering_rejected(self):
        import json, hashlib
        from data.strategy_daily_advice_journal_v1 import encoded
        for mode in ('account','return_digest','return_future_rehashed','return_upgrade_rehashed'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as folder:
                wrapper,journal,clock,response=self.setup_case(folder)
                response.update(status='WAIT',new_orders=[],reference_quotes={})
                wrapper.preview(expected_revision='revision',target_id='target')
                with journal._connection() as database:
                    if mode=='account':
                        database.execute("UPDATE advice_events SET account_id='other'")
                    else:
                        raw=database.execute('SELECT body FROM advice_returns').fetchone()[0]
                        item=json.loads(raw)
                        if mode=='return_future_rehashed':item['checked_at']='2099-01-01T00:00:00+00:00'
                        else:item['status']='READY'
                        raw=encoded(item)
                        if mode=='return_digest':database.execute('UPDATE advice_returns SET body=?',(raw,))
                        else:database.execute('UPDATE advice_returns SET body=?,digest=?',(raw,hashlib.sha256(raw).hexdigest()))
                with self.assertRaises(ValueError):journal.page(account_id='other' if mode=='account' else 'account')

    def test_return_upgrade_and_future_write_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            wrapper,journal,clock,response=self.setup_case(folder)
            response.update(status='WAIT',new_orders=[],reference_quotes={})
            result=wrapper.preview(expected_revision='revision',target_id='target')
            event_id=result['observation_record']['event_id']
            with self.assertRaisesRegex(ValueError,'UPGRADE'):
                journal.record_return(event_id,{'status':'READY','checked_at':clock[0].isoformat()})
            with self.assertRaisesRegex(ValueError,'TIME'):
                journal.record_return(event_id,{'status':'WAIT','checked_at':'2099-01-01T00:00:00+00:00'})
            self.assertEqual(len(journal.page(account_id='account')['items'][0]['event_sha256']),64)

    def test_read_api_rejects_post_read_source_change(self):
        with tempfile.TemporaryDirectory() as folder:
            wrapper,journal,clock,response=self.setup_case(folder)
            wrapper.preview(expected_revision='revision',target_id='target')
            calls=[0]
            def gate():
                calls[0]+=1
                if calls[0]>1:raise ValueError('SOURCE_CHANGED')
            app=FastAPI();app.include_router(create_router(journal=journal,account_id='account',validate_sources=gate))
            with TestClient(app) as client:
                result=client.get('/api/strategy-advice-v1/observations')
                self.assertEqual(result.status_code,409)
                self.assertNotIn('items',result.json())

    def test_hold_wait_are_generation_only(self):
        for status in ('HOLD','WAIT'):
            with tempfile.TemporaryDirectory() as folder:
                wrapper,journal,clock,response=self.setup_case(folder)
                response.update(status=status,new_orders=[],reference_quotes={})
                self.assertEqual(wrapper.preview(expected_revision='revision',target_id='target')['status'],status)
                item=journal.page(account_id='account')['items'][0]
                self.assertEqual(item['generated_status'],status)
                self.assertEqual(item['followup_status'],'NOT_ADMITTED')
                self.assertFalse(item['displayed'])

    def test_future_event_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            wrapper,journal,clock,response=self.setup_case(folder)
            wrapper.preview(expected_revision='revision',target_id='target')
            with journal._connection(readonly=True) as db:
                import json
                event=json.loads(db.execute('SELECT body FROM advice_events').fetchone()[0])
            event['generated_at']=(clock[0]+timedelta(seconds=1)).isoformat()
            with self.assertRaisesRegex(ValueError,'TIME'):journal.append(event,now=clock[0])

if __name__=='__main__':unittest.main()
