from copy import deepcopy
from decimal import localcontext, Inexact, Rounded, ROUND_UP
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from scripts import ndx_return_six_period_account_comparison_20260923 as m
import test_ndx_return_six_period_account_comparison_20260923 as fixtures


class IndependentReview(unittest.TestCase):
    def test_only_labels_may_change(self):
        for edit in (lambda c:c['execution']['trades'][0].update(share_delta=3),
                     lambda c:c['execution']['daily'][0].update(extra='hidden'),
                     lambda c:c.update(promotion_allowed=True)):
            fixture=fixtures.ComparisonTests().raw_fixture();edit(fixture[0])
            with self.assertRaises(ValueError):m.audit_raw(*fixture)

    def test_rejected_share_class_transition_has_no_trade_leg(self):
        old='security:0001652044:02079K107';new='security:0001652044:02079K305'
        execution={'executions':[dict(session='2023-09-01',status='REJECTED',shares_before={old:3},shares_after={old:3})],
                   'trades':[dict(session='2023-09-01',security_id=new,share_delta=3,transaction_cost_usd='1')]}
        with self.assertRaises(ValueError):m.share_class_transition(execution)
        execution['trades']=[]
        self.assertFalse(m.share_class_transition(execution)['class_conversion_inferred'])

    def test_metrics_independent_of_decimal_rounding_and_traps(self):
        values=['100.123']*106+['107.789']
        expected=m.metrics(values)
        with localcontext() as context:
            context.prec=2;context.rounding=ROUND_UP;context.traps[Inexact]=True;context.traps[Rounded]=True
            self.assertEqual(m.metrics(values),expected)
        for invalid in ([True]*107,['NaN']*107,[1]*108):
            with self.assertRaises(ValueError):m.metrics(invalid)

    def test_wrong_hard_candidate_or_producer_rejected_before_sources(self):
        with patch.object(m.archive,'strict') as strict:
            with self.assertRaises(ValueError):m.build('unused','0'*64,m.PRODUCER_SHA)
            strict.assert_not_called()
            with self.assertRaises(ValueError):m.build('unused',m.CANDIDATE_SHA,'0'*64)

    def test_publication_source_drift_does_not_report_success(self):
        with tempfile.TemporaryDirectory() as folder:
            attempt=Path(folder)/'attempt';attempt.mkdir()
            report={'historical_expected_source_hashes':{},'archive_resolution':{},'attempt_directory_entries':[]}
            with patch.object(m,'ACCOUNT_DIRECTORY',attempt),patch.object(m.archive,'load_contract',return_value={}), \
                    patch.object(m.archive,'verify_expected_sources',side_effect=[{}, {'drift':True}]):
                with self.assertRaisesRegex(ValueError,'source drift'):m.publish(report,Path(folder)/'report.json')


if __name__=='__main__':unittest.main()
