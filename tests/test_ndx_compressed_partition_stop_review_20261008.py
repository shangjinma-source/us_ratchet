import unittest
from backtest import ndx_double_replacement_compressed_batch_research as module
from test_ndx_double_replacement_compressed_batch_research import plan, outcome


class Tests(unittest.TestCase):
    def test_numeric_result_cannot_follow_a_stop_in_the_same_batch(self):
        registered = plan()
        for status in module.STATUSES[2:]:
            for resumed in module.STATUSES[:2]:
                row = outcome(registered, 0)
                row['point_runs'] = [dict(start=0, stop=1, status=status),
                                     dict(start=1, stop=512, status=resumed)]
                with self.subTest(status=status, resumed=resumed):
                    with self.assertRaisesRegex(ValueError, 'after within-batch stop'):
                        module.partition(registered, [row])


if __name__ == '__main__':
    unittest.main()
