"""Default constructors with only network transport replaced; original review runs."""
from datetime import timedelta
from email.utils import format_datetime
from unittest.mock import patch
import json
import unittest

from data.strategy_daily_market_capture_v3 import DailyMarketCaptureV3
from data.strategy_account_action_capture_v6 import StrategyAccountActionCaptureV6
from scripts.prepare_profiled_monthly_publication_v1 import prepare
import test_prepare_profiled_monthly_publication_v1 as publication_fixtures


class DefaultCaptureTests(unittest.TestCase):
    def test_default_verified_transports_original_review_and_raw_preserved(self):
        f = publication_fixtures.PublicationTests(); f.setUp(); self.addCleanup(f.doCleanups)
        old_market = f.args.pop('market_capture')
        old_actions = f.args.pop('action_capture')
        f.f.now = f.f.now.replace(microsecond=500000)
        published = f.f.now + timedelta(seconds=1.5)
        raw = ('<rss><channel><title>Nasdaq</title><pubDate>'+format_datetime(published)+
               '</pubDate><item><title>Unrelated</title><pubDate>Tue, 01 Dec 2026 14:00:00 GMT'
               '</pubDate></item></channel></rss>').encode()
        raw = getattr(self, 'saved_rss_bytes', raw)
        market_init, action_init = DailyMarketCaptureV3.__init__, StrategyAccountActionCaptureV6.__init__
        constructed = []
        def make_market(instance, **kwargs):
            market_init(instance, **dict(kwargs, fetch=old_market.fetch))
            constructed.append(type(instance).__name__)
        def make_actions(instance, **kwargs):
            action_init(instance, **dict(kwargs, fetch=old_actions.fetch,
                rss_fetch=lambda:dict(status=200, body=raw)))
            constructed.append(type(instance).__name__)
        def sleep(seconds): f.f.now += timedelta(seconds=seconds)
        before = f.f.store.path.read_bytes()
        with patch.object(DailyMarketCaptureV3, '__init__', make_market), \
             patch.object(StrategyAccountActionCaptureV6, '__init__', make_actions), \
             patch('data.strategy_rss_verified_transport_v3.time.sleep', sleep):
            result = prepare(**f.args)
        self.assertEqual(result['status'], 'PROFILED_MONTHLY_READY_NOT_ADOPTED')
        self.assertEqual(constructed, ['MonthlyReviewMarketCapture', 'MonthlyReviewActionCapture'])
        self.assertEqual(f.f.store.path.read_bytes(), before)
        files = list((f.root/'profile-publication').rglob('*'))
        self.assertTrue(any(p.is_file() and p.suffix == '.xml' and p.read_bytes() == raw for p in files))
        timing = []
        for path in files:
            if path.is_file() and path.suffix == '.json':
                value = json.loads(path.read_bytes())
                if value.get('schema') == 'VERIFIED_RSS_TRANSPORT_TIME_V3': timing.append(value)
        self.assertTrue(timing)
        self.assertTrue(all(v['raw_modified'] is False for v in timing))
        if not hasattr(self, 'saved_rss_bytes'):
            self.assertTrue(all(v['clock_wait_requested_seconds'] > 1 for v in timing))
        self.assertTrue(any(p.name == 'complete-v6.json' for p in files))
        projections = [json.loads(p.read_bytes()) for p in files if p.name == 'complete.json'
                       and json.loads(p.read_bytes()).get('schema') == 'MONTHLY_ACTION_V6_READY_PROJECTION_V1']
        self.assertEqual(len(projections), 1)
        from data.strategy_profiled_release_activation import ProfiledMonthlyReleaseActivation
        from data.strategy_profiled_ready_release import validate_ready_release
        from core.strategy_account_ledger import canonical
        activation = ProfiledMonthlyReleaseActivation(root=f.root,
            initial_snapshot={k:v for k,v in f.snapshot.items() if k!='revision'},
            legacy_anchor=dict(revision=0,record_sha256=None,snapshot=f.snapshot),
            validate_code=lambda:None,clock=lambda:f.f.now)
        ref=result['ready']
        activation.adopt(receipt_path=ref['path'],receipt_sha256=ref['sha256'],expected_release_revision=0)
        projection = next(p for p in files if p.name == 'complete.json' and
            json.loads(p.read_bytes()).get('schema') == 'MONTHLY_ACTION_V6_READY_PROJECTION_V1')
        saved = projection.read_bytes()
        for key,value in [('original_receipts',{}),('original_directory','missing'),
                          ('original_v6_complete_sha256','0'*64)]:
            mutated=json.loads(saved);mutated[key]=value;projection.write_bytes(canonical(mutated))
            with self.assertRaises(ValueError):
                validate_ready_release(root=f.root,receipt_path=ref['path'],receipt_sha256=ref['sha256'],
                    account_state=f.f.store.read(),clock=lambda:f.f.now)
            with self.assertRaises(ValueError): activation.snapshot()
            with self.assertRaises(ValueError):
                activation.adopt(receipt_path=ref['path'],receipt_sha256=ref['sha256'],expected_release_revision=0)
            projection.write_bytes(saved)
        self.assertEqual(activation.snapshot()['revision'],1)


if __name__ == '__main__': unittest.main()
