"""Real capture/parser/compiler path on synthetic transports and temporary files."""
from datetime import datetime
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch, Mock
from core.strategy_account_ledger import canonical
from core.strategy_account_split_v1 import apply_event
from data.strategy_account_action_capture import StrategyAccountActionCapture
from data.current_quantity_v2_paper_action_sources import daily_url
from docs.candidates.strategy_account_split_market_capture import StrategyAccountMarketCapture
from docs.candidates.strategy_account_split_evidence_provider import StrategyAccountEvidenceProvider
from docs.candidates.strategy_account_split_target_inputs import build_target_inputs
import test_strategy_account_evidence_provider as original


class SplitEvidenceProviderTests(unittest.TestCase):
    def test_conflicting_capture_unit_is_not_silently_relabelled(self):
        with TemporaryDirectory() as folder:
            provider, state, _ = self.case(folder)
            capture = provider.market.capture
            def conflicting(**arguments):
                result = capture(**arguments)
                result['marks']['A']['unit_id'] = 'old'
                return result
            provider.market.capture = conflicting
            with self.assertRaisesRegex(ValueError, 'SPLIT_MARK_UNIT_CONFLICT'):
                provider.selection(state)
            self.assertEqual(list(provider.output.glob('*/complete.json')), [])

    def case(self, folder, include_split=True):
        with patch.object(original, 'StrategyAccountEvidenceProvider', StrategyAccountEvidenceProvider), \
             patch.object(original, 'StrategyAccountMarketCapture', StrategyAccountMarketCapture):
            provider, state, now, root = original.ProviderTests().fixture(folder)
        effective = '2026-11-02T14:30:00+00:00'
        action = dict(event_id='split', kind='SPLIT_CONFIRMED', action_id='action', security_id='A', ratio=8,
            effective_at=effective, broker_confirmed_at='2026-11-02T14:31:00+00:00',
            old_unit_id='old', new_unit_id='new', evidence_sha256='a'*64)
        for event in (action, dict(event_id='cash-after', kind='CASH_CONFIRM', amount='80', cash_basis='AVAILABLE_AFTER_RESERVATIONS')):
            state, _ = apply_event(state, event, expected_revision=state['revision'])
        epoch = int(datetime.fromisoformat(effective).timestamp())
        def fetch(ticker, start, end):
            events = {'splits': {str(epoch): dict(date=epoch, numerator=8, denominator=1, splitRatio='8:1')}} if include_split and ticker == 'AAA' else {}
            return dict(status=200, url=daily_url(ticker, start, end), body=canonical(dict(chart=dict(error=None,
                result=[dict(meta=dict(symbol=ticker, currency='USD', instrumentType='EQUITY'), events=events)]))))
        rss = b'<rss><channel><title>Nasdaq</title><item><title>Unrelated</title><pubDate>Mon, 02 Nov 2026 14:00:00 GMT</pubDate></item></channel></rss>'
        provider.actions = StrategyAccountActionCapture(fetch=fetch, rss_fetch=lambda: dict(status=200, body=rss), clock=lambda: now[0])
        provider.limits = Mock(side_effect=AssertionError('selection must not evaluate limits'))
        return provider, state, now

    def test_capture_to_unit_review_to_selection_input(self):
        with TemporaryDirectory() as folder:
            provider, state, now = self.case(folder)
            evidence = provider.selection(state)
            result = build_target_inputs(state=state, now=now[0].isoformat(), maximum_mark_age_seconds=900, **evidence)
            self.assertEqual(result['binding']['strategy_shares']['A'], 16)
            self.assertEqual(result['binding']['marks']['A']['unit_id'], 'new')
            self.assertEqual(result['binding']['strategy_equity'], '260')
            self.assertTrue(result['execution_blocked'])
            provider.limits.assert_not_called()
            self.assertEqual(len(list(provider.output.glob('*/complete.json'))), 1)

    def test_missing_provider_split_blocks_without_success_receipt(self):
        with TemporaryDirectory() as folder:
            provider, state, _ = self.case(folder, include_split=False)
            with self.assertRaisesRegex(ValueError, 'SPLIT_REVIEW_RECORDED_ACTION_MISSING'):
                provider.selection(state)
            self.assertEqual(list(provider.output.glob('*/complete.json')), [])
            self.assertEqual(len(list(provider.output.glob('*/failed.json'))), 1)
            provider.limits.assert_not_called()


if __name__ == '__main__':
    unittest.main()
