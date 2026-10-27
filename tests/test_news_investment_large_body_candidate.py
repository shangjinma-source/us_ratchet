"""Bounded large-body candidate tests; synthetic text only, zero model calls."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from hashlib import sha256

ROOT=Path(__file__).resolve().parents[1]
def load(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/'data'/f'{name.replace("_large_body", "")}.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
S=load('news_investment_sources_large_body_v1')
M=load('news_investment_model_large_body_v1')

class LargeBodyBudgetTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup);self.path=Path(self.folder.name)
        self.positions=[dict(security_id='A',ticker='MRNA',original_qty=1,target_qty=1)]
        self.event=dict(id='s',title='Synthetic test',url='https://example.invalid',tickers=['MRNA'],relevance='company',published_at='2026-10-22T18:59:00Z',collected_at='2026-10-27T18:00:00Z',content_sha256='synthetic')
        self.snapshot=dict(generated_at='2026-10-27T18:01:00Z',events=[self.event],source_receipts=[])
    def test_source_default_and_explicit_budget(self):
        with patch.object(S,'recover',return_value=('x'*89591,'synthetic')):
            self.assertFalse(S.build_sources(self.snapshot,self.path,self.positions)['sources'])
            self.assertEqual(len(S.build_sources(self.snapshot,self.path,self.positions,max_chars=110000)['sources']),1)
        with patch.object(S,'recover',return_value=('x'*110001,'synthetic')):
            self.assertFalse(S.build_sources(self.snapshot,self.path,self.positions,max_chars=110000)['sources'])
        for budget in (110001,True,0):
            with self.assertRaises(ValueError):S.build_sources(self.snapshot,self.path,self.positions,max_chars=budget)
    def test_model_default_unchanged_and_large_body_untruncated(self):
        body='x'*89591
        source=dict(id='s',text=body,security_ids=['A'],content_kind='FULL_TEXT',published_at=self.event['published_at'],observed_at=self.event['collected_at'])
        answer={'rows':[dict(security_id='A',ticker='MRNA',action='ABSTAIN',buy_fraction='1',holding_fraction='1',reason='Synthetic',counterevidence=[],uncertainty=['Synthetic'],evidence=[])]}
        with patch.object(M,'_invoke',return_value=(answer,{})) as invoke:
            self.assertEqual(M.analyze_review([source],self.positions,self.path)['status'],'INPUT_BUDGET_EXCEEDED');invoke.assert_not_called()
            result=M.analyze_review([source],self.positions,self.path,max_chars=120000)
            self.assertEqual(result['status'],'SUCCEEDED');self.assertLess(result['coverage']['prompt_characters'],120000)
            self.assertIn(body,invoke.call_args.args[0]);self.assertEqual(invoke.call_args.args[2],120)
        with patch.object(M,'_invoke') as invoke:
            source['text']='x'*120000
            self.assertEqual(M.analyze_review([source],self.positions,self.path,max_chars=120000)['status'],'INPUT_BUDGET_EXCEEDED');invoke.assert_not_called()
        with self.assertRaises(ValueError):M.analyze_review([source],self.positions,self.path,max_chars=120001)
    def test_service_passes_only_new_budgets(self):
        import runpy
        fixture=runpy.run_path(str(ROOT/'tests/test_news_investment_service_v1.py'))['ServiceTests']();fixture.setUp();self.addCleanup(fixture.doCleanups)
        fixture.service.__class__=load('news_investment_service_large_body_v1').NewsInvestmentService
        fixture.run_job()
        self.assertEqual(fixture.builder.call_args.kwargs['max_chars'],110000)
        self.assertEqual(fixture.model.call_args.kwargs,dict(timeout=120,max_chars=120000))
        self.assertEqual(fixture.model.call_count,1)

if __name__=='__main__':unittest.main()
