from copy import deepcopy
from datetime import datetime,timezone
from hashlib import sha256
import json
from unittest import TestCase
from test_strategy_followup_price_basis_v1 import PriceBasisTests
from data.current_quantity_v2_paper_action_sources import daily_url
from scripts.current_research_official_alert_capture import URL
from data.strategy_followup_close_review_v1 import review_close


class CloseReviewTests(TestCase):
    def fixture(self):
        inputs,source=PriceBasisTests().fixture()
        baseline=json.dumps(dict(chart=dict(error=None,result=[source]))).encode()
        latest=deepcopy(source);latest['timestamp'].append(int(datetime(2026,9,22,14,tzinfo=timezone.utc).timestamp()))
        latest['indicators']['quote'][0]['close'].append(90);latest['indicators']['adjclose'][0]['adjclose'].append(90)
        raw=json.dumps(dict(chart=dict(error=None,result=[latest]))).encode()
        official=b'<rss><channel><pubDate>Wed, 23 Sep 2026 08:00:00 GMT</pubDate><item><title>Other notice</title><pubDate>Wed, 23 Sep 2026 07:00:00 GMT</pubDate><description>Other issuer</description></item></channel></rss>'
        daily=dict(security_id='sid',ticker='TEST',http_status=200,stored_bytes=len(raw),raw_sha256=sha256(raw).hexdigest(),
            started_at='2026-09-23T08:00:00+00:00',received_at='2026-09-23T08:01:00+00:00',
            requested_from='2026-08-01T00:00:00+00:00',requested_through='2026-09-23T08:00:00+00:00')
        daily['url']=daily_url('TEST',datetime.fromisoformat(daily['requested_from']),datetime.fromisoformat(daily['requested_through']))
        rss=dict(http_status=200,stored_bytes=len(official),raw_sha256=sha256(official).hexdigest(),url=URL,
            started_at='2026-09-23T08:02:00+00:00',received_at='2026-09-23T08:03:00+00:00')
        return dict(observation=dict(observation_id='id',security_id='sid',ticker='TEST',side='SELL',reference_session='2026-09-21',
                observation_session='2026-09-22',observation_close='2026-09-22T20:00:00+00:00',reference_limit='100'),
            baseline_inputs=inputs,baseline_files={'raw':baseline,'units':b'{}'},daily_bytes=raw,daily_receipt=daily,
            official_bytes=official,official_receipt=rss,now=datetime(2026,9,23,9,tzinfo=timezone.utc))
    def test_sell_observation_is_price_change_not_trade_profit(self):
        result=review_close(**self.fixture())
        self.assertEqual(result['price_change_vs_reference'],'-1/10')
        self.assertFalse(result['actual_fill_inferred']);self.assertFalse(result['performance_computed'])
    def test_revised_baseline_rejected_even_with_matching_new_hash(self):
        args=self.fixture();source=json.loads(args['daily_bytes']);row=source['chart']['result'][0]
        row['indicators']['quote'][0]['close'][0]=101;row['indicators']['adjclose'][0]['adjclose'][0]=101
        raw=json.dumps(source).encode();args['daily_bytes']=raw;args['daily_receipt'].update(raw_sha256=sha256(raw).hexdigest(),stored_bytes=len(raw))
        with self.assertRaisesRegex(ValueError,'FOLLOWUP_BASELINE_REVISED'):review_close(**args)
    def test_future_capture_and_wrong_ticker_rejected(self):
        args=self.fixture();args['now']=datetime(2026,9,22,21,tzinfo=timezone.utc)
        with self.assertRaisesRegex(ValueError,'FOLLOWUP_CAPTURE_TIME'):review_close(**args)
        args=self.fixture();args['observation']['ticker']='OTHER'
        with self.assertRaisesRegex(ValueError,'FOLLOWUP_BASELINE_TICKER'):review_close(**args)
