import unittest
from copy import deepcopy
from unittest.mock import patch
import test_continuous_guided_capped_next_open as fixture
from backtest.continuous_guided_capped_next_open_v2 import run_capped_next_open


class PrefixTests(unittest.TestCase):
    def test_exact_prefix_skips_search_and_preserves_book(self):
        assembled, bars = fixture.CappedBookTests().data()
        arguments = dict(assembled=assembled, ohlc=bars, initial_cash='1000', fee_bps='0', slippage_bps='5')
        original = run_capped_next_open(**arguments)
        selected = [row['selection'] for row in original['provider_audit'] if row.get('selection')]
        prefix = [dict(arguments=a, selection=s) for a,s in zip(original['selection_account_states'], selected)]
        with patch('backtest.continuous_guided_capped_next_open_v2.decide_capped_account', side_effect=AssertionError('NO_RESEARCH_REPEAT')):
            replay = run_capped_next_open(**arguments, verified_prefix=prefix)
        self.assertEqual(replay['daily_ledger'], original['daily_ledger'])
        self.assertEqual(replay['order_log'], original['order_log'])
        self.assertEqual((replay['reused_searches'], replay['new_searches']), (2, 0))
        bad = deepcopy(prefix)
        bad[0]['arguments']['account_state']['cash'] = '999'
        with patch('backtest.continuous_guided_capped_next_open_v2.decide_capped_account', side_effect=AssertionError('NO_FALLBACK')):
            rejected = run_capped_next_open(**arguments, verified_prefix=bad)
        self.assertEqual(rejected['status'], 'BLOCKED')
        self.assertIn('SAVED_SELECTION_INPUT_MISMATCH', str(rejected['provider_audit']))


if __name__ == '__main__': unittest.main()
