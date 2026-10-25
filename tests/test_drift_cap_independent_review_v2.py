"""A reduced position survives an unrelated after-close wait without rebuying."""
from copy import deepcopy
from fractions import Fraction
import unittest

from backtest.drift_cap_independent_review import review_book as original_review
from backtest.drift_cap_independent_review_v2 import review_book
from test_drift_cap_independent_review import fixture


def wait_fixture():
    book, assembled, bars = fixture()
    quantity = book['shares']['A']
    cash = book['cash']
    equity = book['daily_ledger'][-1]['equity']
    decision, wait_day, last = '2025-01-03', '2025-01-06', '2025-01-07'
    assembled['session_dates'].extend([wait_day, last])
    for day in (wait_day, last):
        assembled['close_prices']['A'][day] = '210'
        bars['A'][day] = dict(open='210', close='210')
    event = dict(event_id='UNRELATED_DISTRIBUTION', effective_date=decision,
                 timing='AFTER_CLOSE', parent_sid='P', post_parent_sid='P', child_sid='C',
                 source_references=['synthetic-event-evidence'])
    assembled['distribution_events'] = [event]
    book['after_close_records'] = [dict(date=decision, phase='AFTER_CLOSE_UNVALUED_STATE',
        cash=cash, shares={'A': quantity, 'P': 0}, distribution_rights=[],
        last_regular_close_equity=equity, post_event_equity=None)]
    for signal, day, waiting in ((decision, wait_day, True), (wait_day, last, False)):
        audit = dict(action='WAIT_POST_ACTION_MARK' if waiting else 'NO_ACTION',
            selection=None, monthly_ceiling={'A': 100}, target_shares={'A': 100 if waiting else quantity},
            orders=[], risk_overlay=dict(state=dict(decision_date='2025-01-01', session_date=signal,
                peaks={'A': '210'}, exited=[], last_closes={'A': '210'},
                unit_ids={'A': 'research-nominal:A'}), effective_target_quantities={'A': 100}))
        if waiting:
            audit['post_close_review'] = dict(status='UNEXPOSED_RISK_DOMAIN_UNCHANGED',
                event_ids=[event['event_id']], decision_date=signal, orders_permitted=False)
        else:
            audit['drift_overlay'] = dict(ceiling={'A': quantity}, effective_targets={'A': quantity},
                day=signal, month='2025-01-01', reductions=[], tradable_equity=equity)
        book['provider_audit'].append(audit)
        book['daily_ledger'].append(dict(date=day, shares={'A': quantity, 'P': 0}, cash=cash,
            stock_value=str(Fraction(quantity * 210)), equity=equity, receivable='0',
            external_flow='0', distribution_rights=[], merger_entitlements=[]))
    book['state_date'] = book['last_valued_date'] = last
    return book, assembled, bars


class IndependentDriftReviewV2Tests(unittest.TestCase):
    def test_reduced_holdings_and_monthly_target_can_differ_during_wait(self):
        book, assembled, bars = wait_fixture()
        self.assertEqual(book['provider_audit'][2]['target_shares'], {'A': 100})
        self.assertEqual(book['daily_ledger'][2]['shares']['A'], 74)
        with self.assertRaises(AssertionError):
            original_review(book, assembled, bars, drift_enabled=True)
        result = review_book(book, assembled, bars, drift_enabled=True)
        self.assertEqual(result['review_version'], 2)
        self.assertEqual(result['fills'], 2)

    def test_unrelated_wait_proof_cannot_hide_exposure_or_lost_state(self):
        book, assembled, bars = wait_fixture()
        mutations = [
            lambda b, a: a['distribution_events'].clear(),
            lambda b, a: a['distribution_events'][0].update(parent_sid='A'),
            lambda b, a: a['distribution_events'][0].update(source_references=[]),
            lambda b, a: b['provider_audit'][2]['post_close_review'].update(event_ids=['other']),
            lambda b, a: b['after_close_records'][0].update(cash='1'),
            lambda b, a: b['after_close_records'][0].update(shares={'A': 100}),
            lambda b, a: b['after_close_records'][0].update(distribution_rights=[{'child': 'C'}]),
            lambda b, a: b['provider_audit'][3]['drift_overlay']['ceiling'].update(A=100),
        ]
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                bad_book, bad_assembled = deepcopy(book), deepcopy(assembled)
                mutate(bad_book, bad_assembled)
                with self.assertRaises(AssertionError):
                    review_book(bad_book, bad_assembled, bars, drift_enabled=True)

    def test_unauthorized_rebuy_fill_and_cash_change_are_rejected(self):
        book, assembled, bars = wait_fixture()
        mutations = [
            lambda b: b['provider_audit'][2]['orders'].append(dict(security_id='A', side='BUY', quantity=26)),
            lambda b: b['order_log'].append(dict(b['order_log'][0], date='2025-01-06')),
            lambda b: b['daily_ledger'][2].update(shares={'A': 100}),
            lambda b: b['daily_ledger'][2].update(cash='1'),
            lambda b: b['provider_audit'][3].update(target_shares={'A': 100}),
        ]
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                bad = deepcopy(book)
                mutate(bad)
                with self.assertRaises(AssertionError):
                    review_book(bad, assembled, bars, drift_enabled=True)

    def test_nonwait_account_risk_and_cost_checks_remain_active(self):
        book, assembled, bars = fixture()
        self.assertEqual(review_book(book, assembled, bars, drift_enabled=True)['fills'], 2)
        for field, value in [('cash', '1'), ('fees', '0'), ('total_return', '10')]:
            with self.subTest(field=field):
                bad = deepcopy(book)
                bad[field] = value
                with self.assertRaises(AssertionError):
                    review_book(bad, assembled, bars, drift_enabled=True)
        book['fee_bps'] = '0'
        with self.assertRaisesRegex(ValueError, 'REGISTERED_COSTS_REQUIRED'):
            review_book(book, assembled, bars, drift_enabled=True)


if __name__ == '__main__':
    unittest.main()
