import math
import random
import unittest

import numpy as np

from backtest.ndx_exact_pareto_frontier_research import ExactParetoFrontier


def scan(frontier, payload, objectives):
    def dominates(left, right):
        return all(a <= b for a, b in zip(left, right)) and any(a < b for a, b in zip(left, right))
    if any(dominates(old_objectives, objectives) for _, old_objectives in frontier):
        return frontier
    return [(old, old_objectives) for old, old_objectives in frontier
            if not dominates(objectives, old_objectives)]+[(payload, objectives)]


class ExactParetoFrontierTests(unittest.TestCase):
    def check_stream(self, objectives):
        actual, expected = ExactParetoFrontier(), []
        for index, pair in enumerate(objectives):
            payload = {'index': index, 'shares': {'A': index}}
            actual.add(payload, pair)
            expected = scan(expected, payload, pair)
            received = actual.items()
            self.assertEqual(received, [p for p, _ in expected])
            for got, (want, _) in zip(received, expected):
                self.assertIs(got, want)

    def test_random_one_thousand_by_one_hundred_exact_scan_overlap(self):
        randomizer = random.Random(95217)
        for stream in range(100):
            self.check_stream([(randomizer.randrange(50)/50., randomizer.randrange(50)/50.)
                               if stream % 2 else (randomizer.random(), randomizer.random())
                               for _ in range(1000)])

    def test_one_ulp_no_tolerance_or_rounding(self):
        up = math.nextafter(1., math.inf)
        down = math.nextafter(1., -math.inf)
        self.check_stream([(1., 1.), (up, down), (down, up), (1., 1.), (down, down)])

    def test_same_x_fee_edges_and_multiple_removals(self):
        self.check_stream([(1., 10.), (2., 9.), (3., 8.), (4., 7.), (2., 6.),
                           (2., 5.), (2., 8.), (1., 5.), (1., 5.), (0., 20.)])

    def test_all_ties_keep_every_payload_and_insertion_order(self):
        self.check_stream([(1., 2.)]*100)
        self.check_stream([(float(i), float(100-i)) for i in range(100)])
        self.check_stream([(float(i), float(100-i)) for i in reversed(range(100))])

    def test_invalid_objectives_do_not_mutate_frontier(self):
        frontier = ExactParetoFrontier()
        payload = {}
        frontier.add(payload, (1., 1.))
        for invalid in ([1., 1.], (), (1.,), (1., 2., 3.), (True, 1.),
                        (np.bool_(True), 1.), (float('nan'), 1.), (float('inf'), 1.), ('1', 1.)):
            with self.assertRaises(ValueError):
                frontier.add(object(), invalid)
            self.assertEqual(frontier.items(), [payload])

    def test_payload_is_reference_but_objectives_are_snapshot(self):
        payload = {'x': 1}
        frontier = ExactParetoFrontier()
        frontier.add(payload, (1., 1.))
        payload['x'] = 999
        self.assertIs(frontier.items()[0], payload)
        copied_list = frontier.items()
        copied_list.clear()
        self.assertEqual(len(frontier.items()), 1)


if __name__ == '__main__':
    unittest.main()
