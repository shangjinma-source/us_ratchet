"""Independent bounded counterexamples; synthetic fixtures only, no actual publication."""
import unittest
from copy import deepcopy
from fractions import Fraction
from test_ndx_dated_risk_chain_display_independent_readback_20261003 import case, inspect, alter_output, m


class ReaderReview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.saved = case()

    def test_shared_control_aggregate_cannot_change_under_same_identity(self):
        bad = deepcopy(self.saved)
        control = next(iter(bad[3].values()))
        control['aggregation']['rows'][0]['aggregation']['saved_literal_total'] = m.ratio(Fraction(999))
        with self.assertRaises(ValueError):
            inspect(bad)

    def test_false_is_not_zero_and_row_zero_is_not_false(self):
        def permission(rows):
            rows[0]['source_bytes_authenticated'] = 0
        def position(rows):
            rows[0]['tracks']['candidate_integer']['rows'][0]['source_row_index'] = False
        def denominator(rows):
            rows[0]['tracks']['candidate_integer']['rows'][0]['aggregation']['stock_denominator_defined'] = 0
        for change in (permission, position, denominator):
            with self.subTest(change=change.__name__), self.assertRaises(ValueError):
                inspect(alter_output(self.saved, change))

    def test_tiny_positive_exact_and_positive_stock_zero_weight_rejected(self):
        value = Fraction(1, 10**400)
        entries = [dict(security_id='a', risk_chain=None, saved_value='1e-400')]
        saved = dict(rows=[dict(risk_chain=None, unknown=True, members=deepcopy(entries), saved_literal_sum=m.ratio(value), normalized_display_share=m.ratio(Fraction(1)))], security_count=1, saved_literal_total=m.ratio(value), unknown_saved_literal_total=m.ratio(value), normalized_display_denominator=m.ratio(value), stock_denominator_defined=True)
        m.inspect_group(saved, entries)
        forged = deepcopy(saved)
        forged['saved_literal_total'] = m.ratio(Fraction(0))
        with self.assertRaises(ValueError):
            m.inspect_group(forged, entries)
        parent, index, shared, controls, raw, output = deepcopy(self.saved)
        original = m.restore(m.loads(raw.splitlines()[0]), shared)
        source = original['tracks']['candidate_integer']
        got = m.loads(output.splitlines()[0])['tracks']['candidate_integer']
        day, risk, row = source['path'][0], source['risk_rows'][0], got['rows'][0]
        day.update(shares={'a': 1}, risk={'actual_weights': {'a': '0'}}, risk_chains={'a': None}, risk_chain_observation_dates={'a': None})
        exposure = dict(security_id='a', saved_stock_weight='0', risk_chain=None, model_observation_date=None)
        risk.update(saved_risk=deepcopy(day['risk']), stock_denominator_status='POSITIVE_STOCK_ONLY', risk_chains={'a': None}, risk_chain_observation_dates={'a': None}, security_exposures=[exposure])
        entry = dict(security_id='a', risk_chain=None, saved_value='0', original_evidence=exposure)
        zero = m.ratio(Fraction())
        row['saved_risk'] = deepcopy(day['risk'])
        row['aggregation'] = dict(rows=[dict(risk_chain=None, unknown=True, members=[entry], saved_literal_sum=zero, normalized_display_share=None)], security_count=1, saved_literal_total=zero, unknown_saved_literal_total=zero, normalized_display_denominator=None, stock_denominator_defined=False)
        with self.assertRaises(ValueError):
            m.inspect_track(got, source, {}, 'integer', original['calendar'])


if __name__ == '__main__':
    unittest.main()
