import copy
import unittest
from test_strategy_monthly_target_charts import ChartsTests
from data.strategy_frontier_target_charts_v1 import StrategyFrontierTargetChartsV1
from core.strategy_account_ledger import require


class FrontierChartsTests(unittest.TestCase):
    def test_added_candidate_real_ohlc_and_proposal_race(self):
        fixture = ChartsTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.publish(quantity=0)
        original = copy.deepcopy(fixture.target)
        fixture.target.update(proposal_id='a'*64, risk_monthly_targets={'sid:AAA': 3})
        class View:
            def current(self):
                return copy.deepcopy(fixture.target)
            def require_proposal(self, *, target_id, expected_proposal_id):
                require(expected_proposal_id == fixture.target['proposal_id'], 'STALE_FRONTIER_PROPOSAL')
        service = StrategyFrontierTargetChartsV1(root=fixture.root, target_service=View())
        args = dict(target_id=original['target_id'], security_id='sid:AAA', expected_proposal_id='a'*64)
        result = service.bars(**args)
        self.assertEqual([b['close'] for b in result['bars']], [11, 12, 13, 14])
        self.assertEqual(result['proposal_id'], 'a'*64)
        self.assertEqual(fixture.target['payload'], original['payload'])
        read = service._read
        def change(*args):
            raw = read(*args)
            fixture.target['proposal_id'] = 'b'*64
            return raw
        service._read = change
        with self.assertRaisesRegex(ValueError, 'STALE_FRONTIER_PROPOSAL'):
            service.bars(**args)

    def test_latest_wrapper_uses_request_local_proposal_context(self):
        import tempfile
        from unittest.mock import patch
        from test_strategy_latest_display_charts_v1 import DisplayTests
        from data.strategy_frontier_latest_display_charts_v1 import FrontierLatestDisplayChartsV1
        with tempfile.TemporaryDirectory() as folder:
            base, context, body, clock = DisplayTests().setup_case(folder)
            context['proposal_id'] = 'a'*64
            def resolver(view, sid, expected):
                require(context['proposal_id'] == expected, 'STALE_FRONTIER_PROPOSAL')
                return copy.deepcopy(context)
            service = FrontierLatestDisplayChartsV1(view=object(), validate_sources=lambda: None,
                output_root=base.output, clock=base.clock, fetch=base.fetch)
            with patch('data.strategy_frontier_latest_display_charts_v1.frontier_display_context', resolver):
                result = service.bars(security_id='SID', expected_proposal_id='a'*64)
                self.assertEqual(result['proposal_id'], 'a'*64)
                self.assertEqual(result['bars'][-1]['close'], 11)
                def change(ticker):
                    context['proposal_id'] = 'b'*64
                    return body[0]
                service.display_options['fetch'] = change
                with self.assertRaisesRegex(ValueError, 'STALE_FRONTIER_PROPOSAL'):
                    service.bars(security_id='SID', expected_proposal_id='a'*64)
