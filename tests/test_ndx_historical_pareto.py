import unittest

from backtest.ndx_historical_pareto import historical_pareto_membership


def candidate(identity, **changes):
    row = dict(
        portfolio_id=identity, source_batch="exact",
        evaluation_semantics_sha256="a" * 64, universe_track="strict",
        selection_date="2024-06-03", return_p50=.5, return_p10=.2,
        max_drawdown_p50=.1, max_drawdown_p90=.2,
        target_012922_distance=.4, turnover=.1,
    )
    row.update(changes)
    return row


class HistoricalParetoTests(unittest.TestCase):
    def test_tradeoffs_and_ties_remain_without_a_portfolio_count_cap(self):
        rows = [candidate("a"), candidate("b"), candidate("dominated", return_p50=.4)]
        rows += [candidate("low_drawdown", return_p50=.3, max_drawdown_p90=.1)]
        self.assertEqual(historical_pareto_membership(rows), ["a", "b", "low_drawdown"])
        self.assertEqual(historical_pareto_membership(list(reversed(rows))),
                         ["a", "b", "low_drawdown"])
        self.assertEqual(len(historical_pareto_membership(
            [candidate(str(index), holding_count=index + 1) for index in range(101)]
        )), 101)

    def test_mixed_coordinates_are_not_pooled(self):
        for key in ("source_batch", "evaluation_semantics_sha256", "universe_track", "selection_date"):
            with self.subTest(key=key), self.assertRaises(ValueError):
                historical_pareto_membership([candidate("a"), candidate("b", **{key: "different"})])

    def test_missing_nonfinite_duplicate_and_boolean_values_are_rejected(self):
        for value in (None, float("nan"), float("inf"), True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                historical_pareto_membership([candidate("a", return_p50=value)])
        with self.assertRaises(ValueError):
            historical_pareto_membership([candidate("a"), candidate("a")])
        with self.assertRaises(ValueError):
            historical_pareto_membership([candidate(" a ")])
        with self.assertRaises(ValueError):
            historical_pareto_membership([candidate("a", turnover=-1)])
        for coordinate in ({"selection_date": "20240603"},
                           {"evaluation_semantics_sha256": "not-a-hash"}):
            with self.subTest(coordinate=coordinate), self.assertRaises(ValueError):
                historical_pareto_membership([candidate("a", **coordinate)])
        self.assertEqual(historical_pareto_membership([]), [])


if __name__ == "__main__":
    unittest.main()
