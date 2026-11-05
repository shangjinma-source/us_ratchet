"""Composition boundary with real selection/execution and a controlled signal.

Does not certify the reader's source admission.
"""
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest
from unittest.mock import patch
import test_split_monthly_factory_20261105 as fixture
from core.strategy_account_ledger import canonical
from data.saved_frontier_monthly_view_v1 import SavedFrontierMonthlyView, SavedFrontierProposalStore
from docs.candidates.split_native_daily_composition_20261105 import build_composition
from docs.candidates.split_native_daily_execution_bridge_20261105 import DailyMixedExecutionBridge, DailyBuyDataWaitExecutionBridge


class Tests(unittest.TestCase):
    def test_current_proposal_to_real_execution_and_stale_signal_rejection(self):
        with TemporaryDirectory() as folder:
            monthly, store, _ = fixture.Tests().case(folder)
            provider = monthly.execution_provider.__self__
            market = next(c.cell_contents for c in provider.market.capture.__closure__ if hasattr(c.cell_contents, 'fetch'))
            original_fetch = market.fetch
            def fetch(ticker):
                raw = json.loads(original_fetch(ticker)); row = raw['chart']['result'][0]
                row['timestamp'] = list(range(row['meta']['currentTradingPeriod']['regular']['start'], row['meta']['regularMarketTime'], 60))
                row['indicators']['quote'][0] = {k: [v] * len(row['timestamp']) for k,v in dict(open=10,high=11,low=9,close=10,volume=10).items()}
                return canonical(raw)
            market.fetch = fetch
            view = SavedFrontierMonthlyView(monthly=monthly, proposals=SavedFrontierProposalStore(Path(folder)/'proposal.sqlite'), validate_sources=monthly.selection._pins)
            state = store.read()
            target = view.generate(event_id='native-daily', reason='INITIAL', expected_revision=state['revision'], previous_target_id=None)
            proposal = view.require_proposal(target_id=target['target_id'], expected_proposal_id=target['proposal_id'])
            now = provider.clock()
            quantities = dict(proposal['payload']['proposed_target_quantities'])
            for sid in state['shares']: quantities.setdefault(sid, 0)
            signal = dict(account_id=state['account_id'], account_revision=state['revision'], target_id=target['target_id'], proposal_id=proposal['proposal_id'], policy_id='CONTROLLED_NATIVE_TEST', evidence_id='controlled', evidence_archive={'fixture':True}, effective_target_quantities=quantities, observed_at=now.isoformat(), available_at=now.isoformat(), valid_from=now.isoformat(), valid_until=(now+timedelta(seconds=60)).isoformat())
            def reader(*args, **kwargs):
                return dict(status='DAILY_SIGNAL_READY', signal=deepcopy(signal), evidence_archive=signal['evidence_archive'])
            service = build_composition(mixed_execution_bridge=DailyMixedExecutionBridge, buy_wait_execution_bridge=DailyBuyDataWaitExecutionBridge, monthly_service=monthly, monthly_view=view, evidence_reader=reader, execution_provider=monthly.execution_provider, clock=provider.clock, policy_execution_enabled=True, policy_id=signal['policy_id'], fee_bps=monthly.selection.fees)
            request = dict(expected_revision=state['revision'], target_id=target['target_id'], expected_proposal_id=proposal['proposal_id'])
            with patch('socket.socket.connect', side_effect=AssertionError('NETWORK_FORBIDDEN')):
                result = service.preview(**request)
            self.assertEqual(result['status'], 'READY')
            self.assertTrue(result['new_orders'])
            self.assertTrue(result['execution_binding'])
            self.assertEqual(store.read(), state)
            signal['account_revision'] = 'stale'
            with self.assertRaisesRegex(ValueError, 'DAILY_SIGNAL_BINDING_MISMATCH'):
                service.preview(**request)
            self.assertEqual(store.read(), state)
            signal['account_revision'] = state['revision']
            for mode in ('missing_buy', 'zero_cash'):
                with self.subTest(mode=mode):
                    if mode == 'missing_buy':
                        market.fetch = lambda ticker: original_fetch(ticker) if ticker == 'BBB' else fetch(ticker)
                    else:
                        market.fetch = fetch
                        store.append(dict(event_id='zero-cash-composition', kind='CASH_CONFIRM', amount='0', cash_basis='TOTAL_UNINVESTED'), expected_revision=state['revision'])
                    current = store.read()
                    signal['account_revision'] = current['revision']
                    request['expected_revision'] = current['revision']
                    with patch('socket.socket.connect', side_effect=AssertionError('NETWORK_FORBIDDEN')):
                        fallback = service.preview(**request)
                    self.assertEqual(fallback['status'], 'READY')
                    self.assertTrue(fallback['new_orders'])
                    self.assertTrue(all(order['side'] == 'SELL' for order in fallback['new_orders']))
                    self.assertEqual(store.read(), current)
                    self.assertEqual(view.current(), target)
                    if mode == 'missing_buy':
                        self.assertEqual(fallback['buy_data_failure'], 'NONCONTIGUOUS_OR_FUTURE_MINUTE')


if __name__ == '__main__': unittest.main()
