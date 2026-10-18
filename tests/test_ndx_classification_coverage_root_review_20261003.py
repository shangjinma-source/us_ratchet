from copy import deepcopy
import unittest
from backtest import ndx_saved_risk_classification_coverage_research as core
from test_ndx_saved_risk_classification_coverage_research import fixture


class Tests(unittest.TestCase):
    def test_coordinate_without_classification_does_not_inflate_coverage(self):
        arguments = fixture()
        arguments['wiring']['rows'][77]['risk_chain'] = 'unclassified'
        output = core.summarize_saved_classification(**arguments)
        self.assertEqual(output['counts']['coordinate_security_count'], 78)
        self.assertEqual(output['counts']['conditional_labeled_security_count'], 77)
        self.assertEqual(output['counts']['unknown_label_rows'], 24)
        self.assertEqual(output['rows'][77]['saved_risk_chain'], 'unclassified')
        self.assertFalse(output['rows'][77]['formally_verified'])
        self.assertEqual(output['counts']['training_selected_security_count'], 77)

    def test_provenance_join_is_identity_based_and_pointer_retains_original_position(self):
        arguments = fixture()
        provenance = arguments['training_panel']['panel']['original_provenance_and_missing']
        provenance.reverse()
        output = core.summarize_saved_classification(**arguments)
        self.assertEqual(output['rows'][0]['training_provenance']['ticker'], 'T0')
        self.assertTrue(output['rows'][0]['training_provenance_reference']['json_pointer'].endswith('/100'))
        self.assertEqual(output['rows'][77]['nonselection_evidence'], ['SAVED_VOLUME_BLOCK'])

    def test_escaped_local_pointer_and_duplicate_security_cannot_hide(self):
        arguments = fixture()
        arguments['wiring']['a/b'] = {'~token': {'observed': '2026-07-19'}}
        arguments['wiring']['rows'][0]['extra_reference'] = {'json_pointer': '/a~1b/~0token'}
        output = core.summarize_saved_classification(**arguments)
        self.assertEqual(output['rows'][0]['local_evidence']['extra_reference']['saved_evidence'],
            {'observed': '2026-07-19'})
        bad = deepcopy(arguments)
        bad['wiring']['rows'][77]['coordinate']['security_id'] = 'security:0'
        with self.assertRaises(ValueError):
            core.summarize_saved_classification(**bad)


if __name__ == '__main__':
    unittest.main()
