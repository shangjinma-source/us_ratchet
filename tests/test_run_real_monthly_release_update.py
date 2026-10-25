"""Isolated producer through real review/adoption, never production account IO."""
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from api.strategy_rolling_composition import ROLLING_SOURCE_PATHS
from core.strategy_account_ledger import canonical
from core.strategy_account_store import StrategyAccountStore
from data.strategy_account_runtime import ACCOUNT_ID
from data.strategy_account_identity import PinnedStrategyIdentity
from data.strategy_account_market_capture import StrategyAccountMarketCapture
from data.strategy_account_action_capture import StrategyAccountActionCapture
from data.current_quantity_v2_paper_action_sources import daily_url
from scripts.run_real_monthly_release_update import run
import test_build_real_monthly_release_entry as entry_fixture


class UpdateTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        helper = entry_fixture.EntryTests()
        self.root, self.args = helper.setup_package(directory.name)
        self.now = datetime.fromisoformat('2026-12-01T15:00:00+00:00')
        self.save = lambda name, value: helper.save(self.root, name, value)
        pins = {}
        for name in ROLLING_SOURCE_PATHS:
            raw = (Path(__file__).resolve().parents[1]/name).read_bytes()
            destination = self.root/name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(raw)
            pins[name] = sha256(raw).hexdigest()
        descriptor = dict(source_pins=pins, registry_path='empty-registry.json',
            registry_sha256=self.save('empty-registry.json', dict(schema='REAL_STRATEGY_MONTHLY_RELEASES_V1', entries=[])),
            archive_path='archive.json', archive_sha256=self.save('archive.json',
                dict(schema='REAL_STRATEGY_RUNTIME_ARCHIVE_V1', entries=[])))
        self.args['descriptor_sha256'] = self.save('approved.json', descriptor)
        self.store = StrategyAccountStore(self.root/'data/strategy_account/real_strategy.sqlite3', clock=lambda:self.now)
        self.store.initialize(ACCOUNT_ID, operation_id='init')
        identity = PinnedStrategyIdentity(self.root, 'auto-identities.json',
            sha256((self.root/'auto-identities.json').read_bytes()).hexdigest())
        row = json.loads((self.root/'auto-identities.json').read_bytes())['candidates'][0]
        self.store.append(dict(event_id='fill',kind='DIRECT_FILL',security_id=row['security_id'],side='BUY',
            quantity=1,price='10',fees='0',executed_at=self.now.isoformat(),identity_evidence=identity(row['ticker'])),
            expected_revision=self.store.read()['revision'])
        self.calls = []
        def fetch(ticker):
            self.calls.append(ticker)
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
        self.args.update(output_directory='update', clock=lambda:self.now, market_capture=market, action_capture=action)

    def test_preflight_and_before_open_no_writes(self):
        before = {p:p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(run(**self.args)['status'], 'PREFLIGHT_ONLY')
        self.now = datetime.fromisoformat('2026-12-01T14:00:00+00:00')
        self.assertEqual(run(**self.args, execute=True)['status'], 'WAITING_MARKET_OPEN')
        self.assertEqual(before, {p:p.read_bytes() for p in self.root.rglob('*') if p.is_file()})
        self.assertEqual(self.calls, [])

    def test_real_review_adopt_and_restart_are_account_readonly(self):
        before = self.store.path.read_bytes()
        result = run(**self.args, execute=True)
        self.assertEqual(result['status'], 'MONTHLY_DATA_RELEASE_ADOPTED')
        self.assertEqual(result['release_revision'], 1)
        count = len(self.calls)
        with patch('scripts.run_real_monthly_release_update.review', side_effect=AssertionError('NO_REPEAT')):
            self.assertEqual(run(**self.args, execute=True), result)
        self.assertEqual(len(self.calls), count)
        self.assertEqual(before, self.store.path.read_bytes())
        self.assertFalse((self.root/'data/strategy_account/monthly_targets.sqlite3').exists())

    def test_failed_review_not_repeated(self):
        with patch.object(self.args['market_capture'], 'capture', side_effect=ValueError('CAPTURE_FAILED')) as capture:
            with self.assertRaisesRegex(ValueError, 'CAPTURE_FAILED'):
                run(**self.args, execute=True)
            with self.assertRaisesRegex(ValueError, 'UPDATE_PARTIAL_REQUIRES_REVIEW'):
                run(**self.args, execute=True)
            self.assertEqual(capture.call_count, 1)
        self.assertTrue((self.root/'update/failed.json').is_file())
        self.assertTrue((self.root/'update/review/candidate/runtime.json').is_file())

    def test_ready_for_different_entry_is_rejected(self):
        from scripts.review_prepare_real_monthly_release import run as real_review
        def altered(**kwargs):
            result = real_review(**kwargs)
            path = result['files']['registry']['path']
            registry = json.loads((self.root/path).read_bytes())
            registry['entries'][0]['publication_path'] = 'other-publication.json'
            result['files']['registry']['sha256'] = self.save(path, registry)
            self.save('update/review/ready.json', result)
            return result
        with patch('scripts.run_real_monthly_release_update.review', side_effect=altered):
            with self.assertRaisesRegex(ValueError, 'UPDATE_READY_ENTRY_MISMATCH'):
                run(**self.args, execute=True)
        self.assertFalse((self.root/'data/strategy_account/active_monthly_releases.sqlite3').exists())


if __name__ == '__main__':
    unittest.main()
