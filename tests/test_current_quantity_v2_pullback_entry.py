from copy import deepcopy
from fractions import Fraction
import unittest

from data.current_quantity_v2_pullback_entry import build_pullback_candidate


def reference():
    identity = dict(security_id='SNDK-ID', ticker='SNDK', session='2026-10-15')
    bars = [dict(identity, start='2026-10-15T09:30:00-04:00',
                 end='2026-10-15T09:31:00-04:00', open='1300', high='1350',
                 low='1276.070', close='1340', volume='100', synthetic=False),
            dict(identity, start='2026-10-15T09:31:00-04:00',
                 end='2026-10-15T09:32:00-04:00', open='1340', high='1360',
                 low='1330', close='1355', volume='100', synthetic=False)]
    return dict(identity, currency='USD', price_basis='CONDITIONAL_PROVIDER_REGULAR_QUOTE_UNITS',
                source_bytes_verified=True, source_hashes={'fixture': 'a' * 64},
                session_open='2026-10-15T09:30:00-04:00',
                session_close='2026-10-15T16:00:00-04:00',
                captured_at='2026-10-15T09:32:15-04:00',
                checked_at='2026-10-15T09:32:16-04:00',
                last_at='2026-10-15T09:32:14-04:00', last_price='1356.800', bars=bars)


def build(ref=None, **changes):
    kwargs = dict(reference=reference() if ref is None else ref,
                  now='2026-10-15T09:32:17-04:00', rebound_fraction='1/2',
                  minimum_discount='1/200', maximum_age_seconds=120, previous_cap=None)
    kwargs.update(changes)
    return build_pullback_candidate(**kwargs)


class PullbackEntryTests(unittest.TestCase):
    def test_user_counterexample_two_explicit_unvalidated_candidates(self):
        original = reference()
        copy = deepcopy(original)
        half = build(original)
        quarter = build(original, rebound_fraction='1/4')
        self.assertEqual(Fraction(half['limit_price']), Fraction('1316.43'))
        self.assertEqual(Fraction(quarter['limit_price']), Fraction('1296.25'))
        self.assertEqual(original, copy)
        self.assertTrue(half['research_only'])
        self.assertFalse(half['performance_validated'])
        self.assertFalse(half['orders_created'])
        self.assertNotEqual(half['reference_valid_until'], half['hypothetical_day_expiry'])

    def test_flat_or_new_low_still_requires_explicit_discount(self):
        for last in ['1276.070', '1200']:
            ref = reference()
            ref['last_price'] = last
            result = build(ref)
            self.assertLess(Fraction(result['limit_price']), Fraction(last))
            self.assertLessEqual(Fraction(result['limit_price']), Fraction(last) * Fraction('199/200'))

    def test_same_session_cap_prevents_higher_candidate(self):
        prior = build()['cap_declaration']
        ref = reference()
        ref['last_price'] = '1450'
        self.assertEqual(build(ref, previous_cap=prior)['limit_price'], prior['limit_price'])
        for field, value in [('security_id', 'OTHER'), ('ticker', 'MU'),
                             ('session', '2026-10-14'), ('policy_id', 'wrong')]:
            cap = deepcopy(prior)
            cap['binding'][field] = value
            with self.assertRaisesRegex(ValueError, 'PRIOR_CAP_BINDING'):
                build(ref, previous_cap=cap)
        with self.assertRaisesRegex(ValueError, 'PRIOR_CAP_BINDING'):
            build(ref, previous_cap=prior, rebound_fraction='1/4')

    def test_missing_duplicate_synthetic_zero_volume_and_future_minutes(self):
        mutations = [lambda r: r['bars'].pop(0), lambda r: r['bars'].pop(),
                     lambda r: r['bars'].append(deepcopy(r['bars'][-1])),
                     lambda r: r['bars'][0].update(synthetic=True),
                     lambda r: r['bars'][0].update(volume='0'),
                     lambda r: r['bars'][1].update(end='2026-10-15T09:33:00-04:00'),
                     lambda r: r['bars'][0].update(ticker='MU'),
                     lambda r: r['bars'][0].update(low='1500'),
                     lambda r: r.update(source_bytes_verified=False),
                     lambda r: r.update(source_hashes={}),
                     lambda r: r.update(last_at='2026-10-15T09:33:00-04:00'),
                     lambda r: r.update(session='2026-10-14')]
        for mutate in mutations:
            ref = reference()
            mutate(ref)
            with self.assertRaises(ValueError):
                build(ref)

    def test_expiry_and_invalid_policy(self):
        with self.assertRaisesRegex(ValueError, 'EXPIRED'):
            build(now='2026-10-15T09:34:00-04:00')
        for changes in [dict(rebound_fraction='0'), dict(rebound_fraction='1'),
                        dict(minimum_discount='0'), dict(minimum_discount=True),
                        dict(maximum_age_seconds=121), dict(maximum_age_seconds=True)]:
            with self.assertRaises(ValueError):
                build(**changes)
        cap = build()['cap_declaration']
        cap['observed_at'] = '2026-10-15T09:33:00-04:00'
        with self.assertRaisesRegex(ValueError, 'PRIOR_CAP_FROM_FUTURE'):
            build(previous_cap=cap)


if __name__ == '__main__':
    unittest.main()
