from copy import deepcopy
from fractions import Fraction
import unittest

from test_current_quantity_v2_pullback_entry import reference
from data.strategy_halt_aware_pullback_entry_v1 import build_pullback_candidate


def sample():
    value=reference()
    first=value['bars'][0]
    # Real trading continues in the partial resumption minute and the next minute.
    value['bars']=[first,dict(first,start='2026-10-15T09:33:00-04:00',end='2026-10-15T09:34:00-04:00'),
                  dict(first,start='2026-10-15T09:34:00-04:00',end='2026-10-15T09:35:00-04:00')]
    value.update(captured_at='2026-10-15T09:35:15-04:00',checked_at='2026-10-15T09:35:16-04:00',
                 last_at='2026-10-15T09:35:14-04:00')
    value['halt_intervals']=[dict(security_id=value['security_id'],ticker=value['ticker'],session=value['session'],
        halted_at='2026-10-15T09:30:54-04:00',resumed_at='2026-10-15T09:33:54-04:00',
        observed_at='2026-10-15T09:34:00-04:00',source_sha256='a'*64)]
    return value


def build(value):
    return build_pullback_candidate(reference=value,now='2026-10-15T09:35:17-04:00',
        rebound_fraction='1/2',minimum_discount='1/200',maximum_age_seconds=120,previous_cap=None)


class HaltAwareEntryTests(unittest.TestCase):
    def test_halt_coverage_uses_real_lows_and_does_not_mutate(self):
        value=sample();before=deepcopy(value)
        result=build(value)
        self.assertEqual(value,before)
        self.assertEqual(Fraction(result['observed_session_low']),Fraction('1276.070'))
        self.assertFalse(result['orders_created'])

    def test_partial_resumption_minute_must_exist(self):
        value=sample();value['bars'].pop(1)
        with self.assertRaisesRegex(ValueError,'NONCONTIGUOUS'):
            build(value)

    def test_ordinary_gap_cannot_be_exempted(self):
        value=sample();value['halt_intervals']=[]
        with self.assertRaisesRegex(ValueError,'NONCONTIGUOUS'):
            build(value)

    def test_active_halt_and_bad_binding_rejected(self):
        mutations=[lambda x:x.update(resumed_at=None),lambda x:x.update(ticker='OTHER'),
                   lambda x:x.update(source_sha256='b'*64),lambda x:x.update(resumed_at='2026-10-15T09:36:00-04:00')]
        for mutation in mutations:
            value=sample();mutation(value['halt_intervals'][0])
            with self.assertRaises(ValueError):build(value)

    def test_real_bar_cannot_overlap_full_halt_minute(self):
        value=sample();value['bars'].insert(1,dict(value['bars'][0],start='2026-10-15T09:31:00-04:00',end='2026-10-15T09:32:00-04:00'))
        with self.assertRaisesRegex(ValueError,'HALT_BAR_OVERLAP'):build(value)

    def test_no_complete_post_resume_bar_rejected(self):
        value=sample();value['halt_intervals'][0].update(resumed_at='2026-10-15T09:34:54-04:00',observed_at='2026-10-15T09:35:00-04:00')
        value['bars'].pop(1)
        with self.assertRaisesRegex(ValueError,'POST_RESUMPTION'):build(value)
