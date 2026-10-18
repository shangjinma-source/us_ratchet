import tempfile
import unittest
from copy import deepcopy
from datetime import timedelta
import test_current_research_intraday_paper_ledger as ledger_tests
from test_current_research_intraday_execution import NOW
from data.current_research_intraday_paper_ledger import apply_intraday_paper_event
from data.current_research_intraday_performance import compute_intraday_paper_performance


class PerformanceTests(unittest.TestCase):
    def fixture(self, root, filled=True):
        helper = ledger_tests.AcceptanceTests()
        state = helper.fixture(root)[3]
        if filled:
            state = apply_intraday_paper_event(state, helper.event(state), now=NOW+timedelta(minutes=6))
        return state

    def arguments(self):
        return dict(now=NOW+timedelta(minutes=6), source_hashes={'saved/raw.json': 'a'*64}, marks={'sndk': dict(
            security_id='sndk', price='1412', observed_at=(NOW+timedelta(minutes=5)).isoformat(),
            received_at=(NOW+timedelta(minutes=5, seconds=1)).isoformat(),
            valid_until=(NOW+timedelta(minutes=7)).isoformat(), price_basis='NOMINAL_PER_CURRENT_SHARE',
            unit_continuity='NO_UNPROCESSED_ACTIONS', source_references=['saved/raw.json'])})

    def test_partial_conservation_fee_once_and_immutable(self):
        with tempfile.TemporaryDirectory() as root:
            state = self.fixture(root); original = deepcopy(state)
            result = compute_intraday_paper_performance(state, **self.arguments())
            self.assertEqual(result['status'], 'COMPLETE')
            self.assertEqual(result['cash'], '18599')
            self.assertEqual(result['equity'], '20011')
            self.assertEqual(result['unrealized_price_pnl'], '12')
            self.assertEqual(result['net_pnl'], '11')
            self.assertEqual(result['total_return'], '11/20000')
            self.assertEqual(result['recorded_fees'], '1')
            self.assertIsNone(result['annualized_return'])
            self.assertFalse(result['source_authenticated'])
            self.assertFalse(result['source_bytes_verified'])
            self.assertEqual(state, original)

    def test_missing_stale_future_units_and_sources_fail_closed(self):
        with tempfile.TemporaryDirectory() as root:
            state = self.fixture(root)
            mutations = [
                ('valid_until', (NOW+timedelta(minutes=6)).isoformat()),
                ('received_at', (NOW+timedelta(minutes=7)).isoformat()),
                ('observed_at', (NOW+timedelta(minutes=7)).isoformat()),
                ('observed_at', (NOW+timedelta(minutes=3)).isoformat()),
                ('unit_continuity', 'ACTION_PENDING'), ('source_references', ['missing']),
                ('price', '1/0'), ('price', True), ('security_id', 'wrong')]
            for key, value in mutations:
                with self.subTest(key=key, value=value):
                    args = self.arguments(); args['marks']['sndk'][key] = value
                    result = compute_intraday_paper_performance(state, **args)
                    self.assertEqual(result['status'], 'INCOMPLETE')
                    self.assertIsNone(result['equity']); self.assertIsNone(result['total_return'])
            result = compute_intraday_paper_performance(state, now=NOW+timedelta(minutes=6))
            self.assertEqual(result['status'], 'INCOMPLETE')

    def test_no_fill_no_quote_no_invented_return(self):
        with tempfile.TemporaryDirectory() as root:
            state = self.fixture(root, filled=False)
            result = compute_intraday_paper_performance(state, now=NOW)
            self.assertEqual(result['status'], 'COMPLETE')
            self.assertEqual(result['equity'], '20000')
            self.assertFalse(result['performance_available'])
            self.assertIsNone(result['total_return']); self.assertIsNone(result['annualized_return'])
            self.assertEqual(result['marks'], {})

    def test_future_recording_or_tampered_state_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            state = self.fixture(root)
            with self.assertRaises(ValueError):
                compute_intraday_paper_performance(state, now=NOW)
            state['cash'] = '20000'
            with self.assertRaises(ValueError):
                compute_intraday_paper_performance(state, **self.arguments())


if __name__ == '__main__':
    unittest.main()
