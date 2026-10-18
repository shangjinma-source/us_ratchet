"""Temporary SQLite and pinned-source tests; no production stores or search."""
from copy import deepcopy
from datetime import datetime
import hashlib
import json
import unittest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
import test_current_research_paper_performance_sources as fixtures
from data.current_research_paper_store import ResearchPaperStore
from data.current_research_paper_service import CurrentResearchPaperService
from data.current_research_paper_performance_service import CurrentPaperPerformanceService


class PerformanceServiceTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.SavedPerformanceTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.root=self.f.f.root;self.directory=self.root/'paper';store=ResearchPaperStore(self.directory)
        self.initial=store.create(self.f.f.initial['account_id'],self.f.f.initial['plan'])
        self.state=store.record_fill(self.initial['account_id'],self.f.f.fill)
        self.account=self.state['account_id'];self.reader=CurrentResearchPaperService(root=self.root,directory=self.directory)._read_account
        self.config=dict(schema='PAPER_PERFORMANCE_SOURCE_CONFIG_V1',calendar_path='report_calendar.json',calendar_source_hashes=self.f.pins)
        self.now=datetime.fromisoformat('2026-10-15T17:00:00-04:00')
        self.service=CurrentPaperPerformanceService(root=self.root,account_reader=self.reader,clock=lambda:self.now,config=self.config,registry_path='registry.json')
    def test_actual_temporary_sources_and_api_no_database_write(self):
        from api import current_research_paper as api
        app=FastAPI();app.include_router(api.router)
        path=self.directory/'research_paper.sqlite3';before=path.read_bytes()
        with patch.object(api,'PERFORMANCE_SERVICE',self.service),TestClient(app) as client:
            response=client.get('/api/research_paper/performance',params=dict(account_id=self.account,expected_revision=self.state['revision'],through_date='2026-10-14'))
            self.assertEqual(response.status_code,200,response.text);r=response.json()
            self.assertEqual(r['status'],'COMPLETE',r);self.assertEqual(r['total_return'],'1/200')
            self.assertEqual(r['expected_revision'],self.state['revision']);self.assertEqual(r['current_plan_id'],self.state['plan']['plan_id'])
            self.assertEqual(r['genesis_research_id'],'a'*24);self.assertFalse(r['total_return_certified'])
            bad=client.get('/api/research_paper/performance',params=dict(account_id=self.account,expected_revision=self.state['revision'],marks='{}'))
            self.assertEqual(bad.status_code,400)
        self.assertEqual(path.read_bytes(),before)
    def test_missing_config_registry_and_zero_day(self):
        no_config=CurrentPaperPerformanceService(root=self.root,account_reader=self.reader,clock=lambda:self.now)
        r=no_config.performance(self.account,self.state['revision'])
        self.assertEqual(r['status'],'INCOMPLETE');self.assertIsNone(r['total_return'])
        (self.root/'registry.json').unlink()
        r=self.service.performance(self.account,self.state['revision'],'2026-10-14')
        self.assertEqual(r['status'],'INCOMPLETE');self.assertIsNone(r['annualized_return'])
        self.now=datetime.fromisoformat('2026-10-14T14:00:00-04:00')
        r=self.service.performance(self.account,self.state['revision'])
        self.assertEqual(r['through_date'],'2026-10-13');self.assertEqual(r['elapsed_calendar_days'],0)
        self.assertEqual(r['recorded_fill_count'],0);self.assertIsNone(r['annualized_return'])
        self.assertEqual(r['excluded_future_fill_count'],1)
    def test_stale_revision_future_and_unclosed_explicit_rejected(self):
        with self.assertRaisesRegex(ValueError,'STALE'):self.service.performance(self.account,'bad','2026-10-14')
        with self.assertRaisesRegex(ValueError,'FUTURE'):self.service.performance(self.account,self.state['revision'],'2026-10-16')
        self.now=datetime.fromisoformat('2026-10-15T12:00:00-04:00')
        with self.assertRaisesRegex(ValueError,'NOT_COMPLETED'):self.service.performance(self.account,self.state['revision'],'2026-10-15')
        self.now=datetime.fromisoformat('2026-10-16T12:00:00-04:00')
        self.assertIn('COVERAGE_ENDED',str(self.service.performance(self.account,self.state['revision'])['issues']))
    def test_revision_race_and_source_drift_fail_closed(self):
        changed=deepcopy(self.state);changed['revision']='changed'
        service=CurrentPaperPerformanceService(root=self.root,account_reader=__import__('unittest.mock').mock.Mock(side_effect=[self.state,changed]),clock=lambda:self.now,config=self.config,registry_path='registry.json')
        with self.assertRaisesRegex(ValueError,'STALE'):service.performance(self.account,self.state['revision'],'2026-10-14')
        (self.root/'AAA.response.bin').write_bytes(b'bad')
        r=self.service.performance(self.account,self.state['revision'],'2026-10-14')
        self.assertEqual(r['status'],'INCOMPLETE');self.assertIsNone(r['total_return'])
    def test_invalid_registry_entry_is_incomplete_without_metrics(self):
        registry=json.loads((self.root/'registry.json').read_bytes())
        registry['entries']['bad-entry']=[]
        (self.root/'registry.json').write_text(json.dumps(registry))
        result=self.service.performance(self.account,self.state['revision'],'2026-10-14')
        self.assertEqual(result['status'],'INCOMPLETE')
        self.assertEqual(result['issues'],[dict(reason='INVALID_SUCCESSOR_REGISTRY_ENTRY')])
        for field in ('total_return','annualized_return','maximum_close_drawdown'):
            self.assertIsNone(result[field])

    def test_same_day_ambiguity_not_arbitrarily_selected(self):
        registry=json.loads((self.root/'registry.json').read_bytes());identifier=next(iter(registry['entries']))
        entry=registry['entries'][identifier];bundle=json.loads((self.root/entry['bundle_path']).read_bytes());bundle['extra_note']='second review'
        raw=json.dumps(bundle).encode();newid=hashlib.sha256(raw).hexdigest();path='second.json';(self.root/path).write_bytes(raw)
        registry['entries'][newid]=dict(entry,bundle_path=path,sha256=newid);(self.root/'registry.json').write_text(json.dumps(registry))
        r=self.service.performance(self.account,self.state['revision'],'2026-10-14')
        self.assertIn('AMBIGUOUS_SESSION',str(r['issues']));self.assertIsNone(r['total_return'])

if __name__=='__main__':unittest.main()
