import unittest
from scripts.assemble_old_continuous_inputs_v1 import exposure_gate


class OldExposureTests(unittest.TestCase):
    def setUp(self):
        self.envelope = dict(prepared_input_candidate=dict(metadata={'old':dict(ticker='SIRI'), 'new':dict(ticker='ABC')},
            source_provenance={'old':dict(segments=[dict(start='2024-01-01',end='2024-09-09',source_path='used')]),
                               'new':dict(segments=[dict(start='2024-01-01',end='2024-12-31',source_path='used')])}),
            provider_event_inventory=[],action_stream_missing=[],dated_identity_transitions=[])
        self.args = dict(decision_date='2024-08-30', account_state=dict(shares={'old':2}))
        self.selection = dict(target_quantities={'new':1})

    def gate(self):
        return exposure_gate(self.envelope,self.args,self.selection,'2024-09-30','2024-09-03')

    def test_unused_source_missing_does_not_block(self):
        self.envelope['action_stream_missing']=[dict(ticker='ABC',source='unused')]
        self.assertTrue(self.gate()['admitted'])

    def test_selected_source_missing_blocks(self):
        self.envelope['action_stream_missing']=[dict(ticker='ABC',source='used')]
        self.assertFalse(self.gate()['admitted'])

    def test_old_identity_conversion_on_liquidation_blocks(self):
        self.envelope['dated_identity_transitions']=[dict(old_sid='old',new_sid='successor',date='2024-09-03')]
        self.assertFalse(self.gate()['admitted'])

    def test_sold_old_identity_future_conversion_does_not_block(self):
        self.envelope['dated_identity_transitions']=[dict(old_sid='old',new_sid='successor',date='2024-09-10')]
        self.assertTrue(self.gate()['admitted'])

    def test_held_identity_conversion_blocks(self):
        self.selection['target_quantities']['old']=2
        self.envelope['dated_identity_transitions']=[dict(old_sid='old',new_sid='successor',date='2024-09-10')]
        self.assertFalse(self.gate()['admitted'])

    def test_unheld_provider_event_does_not_block(self):
        self.envelope['provider_event_inventory']=[dict(ticker='OTHER',date='2024-09-10')]
        self.assertTrue(self.gate()['admitted'])


if __name__ == '__main__':
    unittest.main()
