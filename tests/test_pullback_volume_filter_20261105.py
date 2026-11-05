import unittest
from copy import deepcopy
from docs.candidates.pullback_volume_filter_20261105 import apply_filter


class VolumeFilterTests(unittest.TestCase):
    def fixture(self):
        entry = dict(security_id='s', breakout_date='2025-01-01', confirmation_date='2025-01-03')
        signals = {'2025-01-03': dict(entries=[entry], eligible=['s'], ema={'s': '123'})}
        inventory = {'securities': {'s': {'volume_by_source': {'p': {'2025-01-01': 100, '2025-01-03': 80}}}}}
        review = [dict(security_id='s', breakout='2025-01-01', confirmation='2025-01-03',
                       pairs=[dict(source='p', breakout_volume=100, confirmation_volume=80)],
                       source_conflict=False, raw_contraction=True)]
        return signals, inventory, review

    def test_strict_filter_preserves_nonentries_and_input(self):
        signals, inventory, review = self.fixture()
        old = deepcopy(signals)
        output, rows = apply_filter(signals, inventory, review, [])
        self.assertEqual(output, old)
        self.assertTrue(rows[0]['retained'])
        inventory['securities']['s']['volume_by_source']['p']['2025-01-03'] = 100
        review[0]['pairs'][0]['confirmation_volume'] = 100
        review[0]['raw_contraction'] = False
        output, rows = apply_filter(signals, inventory, review, [])
        self.assertEqual(output['2025-01-03']['entries'], [])
        self.assertEqual(output['2025-01-03']['ema'], old['2025-01-03']['ema'])
        self.assertEqual(output['2025-01-03']['eligible'], ['s'])
        self.assertEqual(signals, old)

    def test_missing_tampered_identity_or_split_fails(self):
        for mutation in ('missing', 'tamper', 'identity', 'split', 'unused'):
            signals, inventory, review = self.fixture()
            actions = []
            if mutation == 'missing': del inventory['securities']['s']['volume_by_source']['p']['2025-01-01']
            if mutation == 'tamper': review[0]['pairs'][0]['confirmation_volume'] = 70
            if mutation == 'identity': review[0]['security_id'] = 'other'
            if mutation == 'split': actions = [dict(security_id='old', new_security_id='s', date='2025-01-02', type='split_identity')]
            if mutation == 'unused': signals['2025-01-03']['entries'] = []
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                apply_filter(signals, inventory, review, actions)


if __name__ == '__main__':
    unittest.main()
