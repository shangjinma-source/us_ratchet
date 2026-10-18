"""Temporary synthetic TOP1 daily continuation, no market input or real account."""
from copy import deepcopy
from datetime import datetime
import unittest
from unittest.mock import patch

import test_current_research_successor_prepare as prepare_fixtures
from test_current_research_monthly_plan import session
from data.current_research_limit_plan import build_current_research_limit_plan
from data.current_research_fill_ledger import initialize_paper_ledger, apply_paper_fill, apply_paper_order_event
from data.current_research_successor_prepare import prepare_successor_input, save_prepared_input
from data.current_research_successor_inputs import SuccessorInputLoader
from data.current_research_paper_store import ResearchPaperStore
from data.current_research_paper_service import CurrentResearchPaperService
from data.current_research_successor_service import CurrentResearchSuccessorService
from backtest.return_priority_monthly_top1_selector import VERSION


class Top1DailyRollTests(unittest.TestCase):
    def test_partial_expiry_prepare_loader_preview_activation_preserves_top1(self):
        fixture = prepare_fixtures.PrepareTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        causal = deepcopy(fixture.initial['plan']['causal_inputs'])
        snapshot = causal['research_snapshot']
        snapshot.update(selection_method=VERSION, target_month='2026-10',
                        market_session=dict(session('2026-10-14'), source='evidence'))
        plan = build_current_research_limit_plan(research_snapshot=snapshot,
            quotes=[dict(value, security_id=key) for key, value in causal['quotes'].items()],
            available_cash='100', shares={}, account_revision='initial', decision_date='2026-10-13',
            active_date='2026-10-14', calendar=['2026-10-13', '2026-10-14'],
            strategy_version='PAPER_FROZEN_TOP1_V1', target_quantities={'A': 2})
        account = 'paper-' + plan['plan_id'][:24]
        initial = initialize_paper_ledger(plan, account)
        fill = dict(fixture.fill, plan_id=plan['plan_id'], order_id=plan['orders'][0]['order_id'],
                    qty=1, expected_revision=initial['revision'])
        partial = apply_paper_fill(initial, fill)
        expiry = dict(event_id='expiry', mode='PAPER_MANUAL_FILL', event_type='EXPIRE',
                      plan_id=plan['plan_id'], order_id=plan['orders'][0]['order_id'],
                      expected_revision=partial['revision'], completed_session='2026-10-14')
        state = apply_paper_order_event(partial, expiry)
        args = dict(fixture.kw, expected_revision=state['revision'])
        prepared = prepare_successor_input(state, raw_sources=fixture.raw(), **args)
        saved = save_prepared_input(prepared, root=fixture.root, relative_directory='top1-prepared', registry_path='top1-registry.json')
        loader = SuccessorInputLoader(root=fixture.root, registry_path='top1-registry.json')
        base = CurrentResearchPaperService(root=fixture.root, directory=fixture.root/'top1-paper',
            clock=lambda: datetime.fromisoformat('2026-10-14T17:00:00-04:00'))
        store = ResearchPaperStore(base.directory)
        store.create(account, plan)
        store.record_fill(account, fill)
        store.record_order_event(account, expiry)
        service = CurrentResearchSuccessorService(base_service=base, input_provider=loader)
        with patch('backtest.return_priority_monthly_top1_selector.select_top1_quantities', side_effect=AssertionError('No selection allowed')):
            found = service.available_input(account, state['revision'])
            self.assertEqual(found['input_id'], saved['input_id'])
            preview = service.preview(account, saved['input_id'], state['revision'])
            self.assertEqual(preview['route']['action'], 'ROLL')
            self.assertEqual(preview['search_calls_this_request'], 0)
            self.assertEqual(preview['plan']['target_quantities'], {'A': 2})
            self.assertEqual(len(preview['plan']['orders']), 1)
            self.assertEqual(preview['plan']['orders'][0]['quantity'], 1)
            self.assertEqual(preview['plan']['research_id'], plan['research_id'])
            self.assertEqual(preview['plan']['causal_inputs']['research_snapshot']['selection_method'], VERSION)
            self.assertTrue(service.preview(account, saved['input_id'], state['revision'])['cache_hit'])
            output = service.activate(account, preview['preview_id'], 'activate', state['revision'])
            replay = service.activate(account, preview['preview_id'], 'activate', state['revision'])
        self.assertTrue(replay['idempotent_replay'])
        current = store.read(account)
        self.assertEqual((current['cash'], current['shares']), ('90', {'A': 1}))
        self.assertEqual(len(current['plans']), 2)
        self.assertEqual(output['market_session']['date'], '2026-10-15')


if __name__ == '__main__':
    unittest.main()
