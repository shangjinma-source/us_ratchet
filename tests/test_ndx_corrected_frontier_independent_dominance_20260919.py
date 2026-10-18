from copy import deepcopy
import unittest
from scripts import ndx_corrected_frontier_independent_dominance_20260919 as m


class Tests(unittest.TestCase):
    def fixture(self):
        columns = ['c' + str(i) for i in range(8)]
        rows = [dict(job_id=str(i), benchmark_differences=dict(zip(columns, values))) for i, values in enumerate(
            ([2]*8, [2]*8, [1]*8, [3,0,0,0,0,0,0,0]))]
        return rows, columns

    def test_exact_ties_and_incomparable_kept(self):
        rows, columns = self.fixture()
        result = m.prove(rows, [rows[0], rows[1], rows[3]], columns, [1]*8)
        self.assertEqual(result['strictly_dominated_omissions'], 1)

    def test_omitted_tie_dominated_inclusion_and_changed_metric_reject(self):
        rows, columns = self.fixture()
        for selected in ([rows[0], rows[3]], rows, [rows[0], rows[1]]):
            with self.assertRaises(ValueError): m.prove(rows, selected, columns, [1]*8)
        selected = deepcopy([rows[0], rows[1], rows[3]])
        selected[0]['benchmark_differences']['c0'] = 100
        with self.assertRaises(ValueError): m.prove(rows, selected, columns, [1]*8)

    def test_negative_direction_and_empty(self):
        rows, columns = self.fixture()
        self.assertEqual(m.prove(rows, [rows[2], rows[3]], columns, [-1]*8)['frontier_count'], 2)
        self.assertEqual(m.prove([], [], columns, [1]*8)['candidate_count'], 0)
        with self.assertRaises(ValueError): m.prove(rows, [], columns, [1]*8)
        with self.assertRaises(ValueError): m.prove(rows, [rows[0], rows[1], rows[3]], columns, [True]*8)


if __name__ == '__main__': unittest.main()
