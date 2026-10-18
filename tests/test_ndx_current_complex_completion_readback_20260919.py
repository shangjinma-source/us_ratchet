import unittest
from scripts import ndx_current_complex_completion_readback_20260919 as m


class Tests(unittest.TestCase):
    def test_actual_missing_2026_tri_action_and_complex_policy(self):
        result = m.build()
        rows = {r['ticker']: r for r in result['rows']}
        self.assertFalse(rows['TRI']['specific_boundary_in_returned_events'])
        self.assertEqual(rows['TRI']['first_post_action_session_candidate'], '2026-05-04')
        self.assertTrue(rows['CMCSA']['specific_boundary_in_returned_events'])
        self.assertTrue(rows['CMCSA']['parent_split_ratio_not_inferred_from_distribution'])
        self.assertFalse(result['all_company_actions_covered'])
        self.assertFalse(result['quote_reconstruction_performed'])
        self.assertFalse(result['point_in_time_verified'])

    def test_without_exact_dated_completion_cannot_claim_boundary(self):
        for texts in (('', '', ''), ('January 5, 2026', '', ''),
                      ('completion of its previously announced separation', '', 'On May 4, 2026')):
            with self.subTest(texts=texts), self.assertRaises(ValueError):
                m.extract(*texts)


if __name__ == '__main__':
    unittest.main()
