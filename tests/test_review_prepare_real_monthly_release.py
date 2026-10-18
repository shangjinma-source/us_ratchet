from datetime import datetime
from pathlib import Path
import unittest
from core.strategy_account_ledger import canonical
from core.strategy_account_store import StrategyAccountStore
from data.strategy_account_runtime import ACCOUNT_ID
from data.strategy_account_identity import PinnedStrategyIdentity
from data.strategy_account_market_capture import StrategyAccountMarketCapture
from data.strategy_account_action_capture import StrategyAccountActionCapture
from data.current_quantity_v2_paper_action_sources import daily_url
from scripts.review_prepare_real_monthly_release import run
import test_strategy_account_monthly_release as release_fixture


class ReviewPrepareTests(unittest.TestCase):
    def setUp(self):
        self.f=release_fixture.MonthlyReleaseTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.root=self.f.root;self.now=datetime.fromisoformat('2026-12-01T15:00:00+00:00')
        self.store=StrategyAccountStore(self.root/'data/strategy_account/real_strategy.sqlite3',clock=lambda:self.now)
        self.store.initialize(ACCOUNT_ID,operation_id='init')
        identity=PinnedStrategyIdentity(self.root,'identity-release.json',self.f.entry['identity_sha256'])
        row=self.f.identity['candidates'][0]
        self.store.append(dict(event_id='fill',kind='DIRECT_FILL',security_id=row['security_id'],side='BUY',
            quantity=1,price='10',fees='0',executed_at=self.now.isoformat(),identity_evidence=identity(row['ticker'])),
            expected_revision=self.store.read()['revision'])
        def fetch(ticker):
            start=int(datetime.fromisoformat('2026-12-01T14:30:00+00:00').timestamp());last=start+1800
            return canonical(dict(chart=dict(error=None,result=[dict(meta=dict(symbol=ticker,currency='USD',
                instrumentType='EQUITY',exchangeTimezoneName='America/New_York',dataGranularity='1m',regularMarketPrice=10,
                regularMarketTime=last,currentTradingPeriod=dict(regular=dict(start=start,end=start+23400))),
                timestamp=[last-60],indicators=dict(quote=[dict(open=[10],high=[11],low=[9],close=[10],volume=[10])]))])))
        market=StrategyAccountMarketCapture(identity_resolver=identity,fetch=fetch,clock=lambda:self.now)
        def actions(t,start,end):
            return dict(status=200,url=daily_url(t,start,end),body=canonical(dict(chart=dict(error=None,result=[
                dict(meta=dict(symbol=t,currency='USD',instrumentType='EQUITY'),events={})]))))
        action=StrategyAccountActionCapture(fetch=actions,rss_fetch=lambda:dict(status=200,
            body=b'<rss><channel><title>Nasdaq</title><item><title>Unrelated</title><pubDate>Tue, 01 Dec 2026 14:00:00 GMT</pubDate></item></channel></rss>'),clock=lambda:self.now)
        self.arguments=dict(root=self.root,registry_path='empty-registry.json',registry_sha256=self.f.put('empty-registry.json',
            dict(schema='REAL_STRATEGY_MONTHLY_RELEASES_V1',entries=[])),archive_path='archive.json',archive_sha256=self.f.put('archive.json',
            dict(schema='REAL_STRATEGY_RUNTIME_ARCHIVE_V1',entries=[])),new_entry=self.f.entry,output_directory='reviewed-package',
            clock=lambda:self.now,market_capture=market,action_capture=action)

    def test_real_prepare_review_outputs_ready_without_account_changes(self):
        before=self.store.path.read_bytes()
        result=run(**self.arguments)
        self.assertEqual(result['status'],'READY_FOR_ACTIVATION_NOT_ACTIVATED')
        self.assertEqual(set(result['files']),{'registry','archive','runtime','unit_review','complete'})
        self.assertFalse(self.store.read()['cash_confirmation_valid'])
        self.assertEqual(self.store.path.read_bytes(),before)
        self.assertTrue((self.root/'reviewed-package/ready.json').is_file())
        self.assertFalse((self.root/'data/strategy_account/monthly_targets.sqlite3').exists())
        with self.assertRaisesRegex(ValueError,'REVIEW_PREPARE_OUTPUT_CONFLICT'):run(**self.arguments)

    def test_review_failure_preserves_candidate_and_never_ready(self):
        def fail(**kwargs):raise ValueError('SYNTHETIC_CAPTURE_FAILED')
        self.arguments['market_capture'].capture=fail
        with self.assertRaisesRegex(ValueError,'SYNTHETIC_CAPTURE_FAILED'):run(**self.arguments)
        self.assertTrue((self.root/'reviewed-package/candidate/runtime.json').is_file())
        self.assertTrue((self.root/'reviewed-package/failed.json').is_file())
        self.assertFalse((self.root/'reviewed-package/ready.json').exists())

    def test_concurrent_revision_prevents_ready(self):
        action=self.arguments['action_capture'];original=action.capture
        def changed(*args,**kwargs):
            result=original(*args,**kwargs)
            self.store.append(dict(event_id='cash',kind='CASH_CONFIRM',amount='100',cash_basis='TOTAL_UNINVESTED'),
                expected_revision=self.store.read()['revision'])
            return result
        action.capture=changed
        with self.assertRaisesRegex(ValueError,'ACCOUNT_CHANGED_DURING_REVIEW'):run(**self.arguments)
        self.assertFalse((self.root/'reviewed-package/ready.json').exists())
        self.assertTrue((self.root/'reviewed-package/failed.json').is_file())


if __name__=='__main__':unittest.main()
