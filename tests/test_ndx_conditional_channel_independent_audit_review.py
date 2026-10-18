import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_ndx_conditional_channel_input_research import fixture
from test_ndx_conditional_channel_actual_fixtures import fixture as actual_fixture
from backtest import ndx_conditional_channel_input_research as producer
from backtest import ndx_conditional_channel_independent_audit_research as oracle


def audit_arguments(inputs, output):
    return dict(output=output, **{key: inputs[key] for key in (
        'raw_bytes', 'quote_rows', 'calendar', 'event_policy', 'exclude_on_or_after', 'regular_floor')})


class OracleReviewTests(unittest.TestCase):
    def test_unrecognised_authorization_or_identity_fields_refused(self):
        inputs = fixture(); output = producer.build_channel_input(**inputs)
        for key, value in (('execution_authorized', True), ('search_admission_allowed', True),
                           ('security_id', 'security:invented')):
            changed = copy.deepcopy(output); changed[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                oracle.audit(**audit_arguments(inputs, changed))

    def test_disguised_volume_qualification_and_return_change_reject(self):
        inputs = fixture(80); output = producer.build_channel_input(**inputs)
        changed = copy.deepcopy(output); changed['liquidity']['numerical_threshold_passed'] = True
        with self.assertRaises(ValueError):
            oracle.audit(**audit_arguments(inputs, changed))
        changed = copy.deepcopy(output); changed['price_returns'][79]['price_return'] += 0.01
        with self.assertRaises(ValueError):
            oracle.audit(**audit_arguments(inputs, changed))

    def test_actual_six_channels_have_independent_raw_oracle(self):
        for ticker in ('KLAC', 'BKNG', 'MNST', 'CRWD', 'CDNS', 'EXC'):
            with self.subTest(ticker=ticker):
                inputs = actual_fixture(ticker)
                output = producer.build_channel_input(**inputs)
                report = oracle.audit(**audit_arguments(inputs, output))
                self.assertEqual(report['return_count'], 126)
                self.assertFalse(report['producer_called'])
                self.assertFalse(report['legal_training_input_admitted'])


if __name__ == '__main__':
    unittest.main()
