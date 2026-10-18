"""Bounded independent stream-selector review; no production result consumption."""
from copy import deepcopy
import unittest
from backtest import ndx_cash_neighbor_stream_selection_research as m
from test_ndx_cash_neighbor_selection_research import fixture


def second(record):
    out = deepcopy(record)
    out['task']['scenario_candidate_ordinal'] = 1
    out['task']['identity']['buy_shares'] = {'A': 4}
    out['task']['task_id'] = m.digest(out['task']['identity'])
    out['raw']['result']['branches'][0]['evaluated_plans'][0]['buy_shares'] = {'A': 4}
    out['shard_audit']['document']['detail']['task_results'][0]['task_id'] = out['task']['task_id']
    return out


def saved_score(record, numerator, denominator, fee):
    score = dict(distance=dict(numerator=numerator, denominator=denominator), fees_usd=dict(numerator=fee, denominator=1))
    record['raw']['result']['branches'][0]['evaluated_plans'][0]['fees_usd'] = str(fee)
    record['postcheck']['original_target_stock_weight_l1'] = deepcopy(score)
    record['shard_audit']['document']['detail']['task_results'][0]['original_target_stock_weight_l1'] = deepcopy(score)


class StreamReview(unittest.TestCase):
    def test_emitted_alias_cannot_rewrite_winner_or_original_input(self):
        args = fixture()
        before = deepcopy(args)
        retained = []
        result = m.select_scenario_stream(**args, emit_ledger_row=retained.append)
        retained[-1]['saved_plan']['proposed_holdings']['A'] = 999
        retained[-1]['buy_shares']['A'] = 999
        retained[0]['references']['plan']['path'] = 'changed'
        self.assertEqual(args, before)
        self.assertEqual(result['selected']['buy_shares'], {'A': 3})
        self.assertEqual(result['selected']['saved_plan']['proposed_holdings'], {'A': 3})
        self.assertNotIn('candidate_ledger', result)
        self.assertIs(result['ledger_emitter_source_authenticated'], False)
        def mutate(row): row['saved_plan']['feasible'] = False
        with self.assertRaises(ValueError):
            m.select_scenario_stream(**args, emit_ledger_row=mutate)

    def test_mutable_single_record_iterator_is_processed_before_next_yield(self):
        args = fixture()
        one = args['new_records'][0]
        two = second(one)
        emitted = []
        mutable = deepcopy(one)
        def records():
            self.assertEqual(len(emitted), 2)
            yield mutable
            self.assertEqual(len(emitted), 3)
            mutable.clear(); mutable.update(deepcopy(two))
            yield mutable
            self.assertEqual(len(emitted), 4)
        args.update(new_records=records(), expected_new_count=2)
        result = m.select_scenario_stream(**args, emit_ledger_row=emitted.append)
        self.assertEqual([r['buy_shares']['A'] for r in emitted], [1, 2, 3, 4])
        self.assertEqual(result['selected']['buy_shares'], {'A': 3})
        self.assertEqual(result['ledger_emitted_row_count'], 4)

    def test_terminal_iterator_failure_or_truncation_never_returns_success(self):
        for mode in ('missing_last', 'failure_after_last'):
            args = fixture()
            record = args['new_records'][0]
            def records():
                yield record
                if mode == 'failure_after_last': raise OSError('synthetic source tail failed')
            args.update(new_records=records(), expected_new_count=2 if mode == 'missing_last' else 1)
            emitted = []
            with self.subTest(mode=mode), self.assertRaises((ValueError, OSError)):
                m.select_scenario_stream(**args, emit_ledger_row=emitted.append)
            self.assertEqual(len(emitted), 3)

    def test_exact_fraction_tie_fee_then_ordinal(self):
        args = fixture()
        first = args['new_records'][0]
        later = second(first)
        saved_score(first, 1, 3, 2)
        saved_score(later, 2, 6, 1)
        args.update(new_records=[first, later], expected_new_count=2)
        result = m.select_scenario_stream(**args, emit_ledger_row=lambda row: None)
        self.assertEqual(result['selected']['buy_shares'], {'A': 4})
        saved_score(first, 1, 3, 1)
        result = m.select_scenario_stream(**args, emit_ledger_row=lambda row: None)
        self.assertEqual(result['selected']['buy_shares'], {'A': 3})
        self.assertEqual(result['total_candidate_count'], 4)
        self.assertEqual(result['feasible_candidate_count'], 3)


if __name__ == '__main__': unittest.main()
