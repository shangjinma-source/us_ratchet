from datetime import datetime, timezone
from hashlib import sha256
import json
from tempfile import TemporaryDirectory
import unittest

from core.strategy_account_ledger import canonical, replay
from data.saved_frontier_source_review_v1 import review_proposal_monthly_sources
from data.strategy_monthly_supplement_capture import capture_supplement
from test_monthly_peak_raw_history import MonthlyRawHistoryTests


class FrontierSourceReviewTests(unittest.TestCase):
    def test_fresh_conditional_review_and_expired_session(self):
        inputs, series = MonthlyRawHistoryTests().fixture()
        inputs['base_target']['origin_reference'] = 'proposal'
        state = replay('test', [])
        now = datetime(2026, 10, 6, 14, tzinfo=timezone.utc)
        binding = dict(target_id='target', account_id='test',
            account_revision=state['revision'],
            session='2026-10-06')
        request = dict(account_id='test', state_revision=state['revision'],
            window_start='2026-10-01T13:30:00+00:00', observed_floor=now.isoformat(),
            securities={'A': {'ticker': 'TEST'}}, current_target_quantities={'A': 10})
        rss = b'<rss><channel><pubDate>Tue, 06 Oct 2026 13:00:00 GMT</pubDate><item><title>Other issuer notice</title><pubDate>Tue, 06 Oct 2026 13:00:00 GMT</pubDate></item></channel></rss>'
        with TemporaryDirectory() as folder:
            capture = capture_supplement(directory=folder, request=request, binding=binding,
                read_binding=lambda: binding, execute=True, clock=lambda: now,
                fetch_daily=lambda *a: dict(status=200, body=json.dumps(dict(chart=dict(error=None, result=[series]))).encode()),
                fetch_official=lambda: dict(status=200, body=rss))
            args = dict(target=dict(target_id='target', payload=dict(account_id='test', target_month='2026-10')),
                proposal=dict(proposal_id='proposal', payload=dict(proposed_target_quantities={'A': 10})),
                state=state, risk_state=None, inputs=inputs, identities={'A': dict(ticker='TEST', exchange='NMS')},
                capture=capture, request=request, execution_session=dict(date='2026-10-06',
                    open='2026-10-06T13:30:00+00:00', close='2026-10-06T20:00:00+00:00'))
            result = review_proposal_monthly_sources(**args, now=now)
            self.assertTrue(result['full_price_window_verified'])
            self.assertFalse(result['coverage_complete'])
            self.assertEqual(result['reviewed_at'], now.isoformat())
            with self.assertRaisesRegex(ValueError, 'WAIT_FRONTIER_CURRENT_EXECUTION_SESSION'):
                review_proposal_monthly_sources(**args, now='2026-10-07T14:00:00+00:00')
            args['proposal']['payload']['proposed_target_quantities']['B'] = 1
            with self.assertRaisesRegex(ValueError, 'FRONTIER_COMPLETE_REQUIRED_DOMAIN'):
                review_proposal_monthly_sources(**args, now=now)
