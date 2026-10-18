import copy
import unittest
from unittest.mock import patch
from test_ndx_single_window_account_comparison_20260920 import fixture, recovery_fixture
from scripts import ndx_single_window_account_comparison_20260920 as m


class ComparisonIndependentReview(unittest.TestCase):
    def test_control_recovery_original_bytes_and_failure_are_not_relabelled(self):
        baseline = recovery_fixture()
        for defect in ('cash', 'source', 'schema', 'replay', 'reference'):
            args=list(copy.deepcopy(baseline));account,raw=args[:2]
            if defect=='cash':
                account['execution']['daily'][2]['cash_usd']+=1
                raw['execution']['daily'][2]['cash_usd']+=1
            elif defect=='source':account['original_execution_source_hashes']={}
            elif defect=='schema':account['schema']='HISTORICAL_SINGLE_WINDOW_CONDITIONAL_ACCOUNT_V1'
            elif defect=='replay':account['execution_replayed']=0
            else:account['recovery_failure_reference']=dict(account['recovery_failure_reference'],sha256='0'*64)
            with self.subTest(defect=defect),self.assertRaises(ValueError):m.inspect(*args)
        import json
        from pathlib import Path
        failure=json.loads(Path(m.CONTROL_REFS['failure']['path']).read_bytes())
        m.check_original_failure(failure)
        for key,value in [('automatic_retry_allowed',True),('failure_is_economic_infeasibility',True),('engine_call_started',1),('error_type','RiskFailure')]:
            changed=copy.deepcopy(failure);changed[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):m.check_original_failure(changed)

    def test_coherent_raw_and_account_cash_edit_still_fails_independent_oracle(self):
        for defect in ('cash', 'date', 'normalization'):
            args = list(copy.deepcopy(fixture()))
            account, raw = args[:2]
            if defect == 'cash':
                for execution in (account['execution'], raw['execution']):
                    execution['daily'][10]['cash_usd'] += 1
                    execution['daily'][10]['total_value_usd'] += 1
            elif defect == 'date':
                for execution in (account['execution'], raw['execution']):
                    execution['daily'][10]['session'] = execution['daily'][11]['session']
            else:
                for execution in (account['execution'], raw['execution']):
                    targets = execution['decisions'][0]['targets']
                    targets[next(iter(targets))]['target_weight'] += 1e-10
            with self.subTest(defect=defect), self.assertRaises(ValueError):
                m.inspect(*args)

    def test_saved_reconstruction_preserves_raw_and_conditional_scope(self):
        args = fixture()
        before = copy.deepcopy(args[1])
        m.inspect(*args)
        self.assertTrue(m.exact(args[1], before))
        for key in ('independent_accounting_completed', 'point_in_time_verified'):
            changed = list(copy.deepcopy(args))
            changed[1][key] = 0  # False and numeric zero are not interchangeable evidence.
            with self.subTest(key=key), self.assertRaises(ValueError): m.inspect(*changed)

    def test_full_report_publish_rejects_resigned_partition_and_permissions(self):
        baseline = dict(schema='HISTORICAL_SINGLE_WINDOW_ACCOUNT_COMPARISON_V1',
                        historical_expected_source_hashes={'required':'a'*64},
                        archive_resolution={'verified':'original'},
                        promotion_allowed=False)
        for defect in ('source', 'permission', 'extra'):
            changed = copy.deepcopy(baseline)
            if defect == 'source':
                changed['historical_expected_source_hashes'] = {}
                changed['archive_resolution'] = {}
            elif defect == 'permission': changed['promotion_allowed'] = True
            else: changed['historical_pit_approved'] = True
            with self.subTest(defect=defect), patch.object(m,'build',return_value=baseline), patch.object(m,'publish') as publisher:
                with self.assertRaises(ValueError): m.publish_verified('unused.json',changed)
                publisher.assert_not_called()

    def test_original_nav_never_uses_future_and_127_is_not_126(self):
        args = fixture()
        calendar = args[3]['calendar']
        daily = args[0]['execution']['daily']
        value = m.metrics.compare(calendar=calendar,candidate_daily=daily,incumbent_daily=daily,
                                  nav_csv='Date,Close\n2026-03-17,1\n2026-09-18,999\n')
        self.assertEqual(value['candidate']['return_interval_count'],126)
        self.assertTrue(all(row['nav_source_date']=='2026-03-17' for row in value['nav']['rows']))
        self.assertFalse(value['formal_dual_benchmark_admission'])
        with self.assertRaises(ValueError):
            m.metrics.compare(calendar=calendar[1:],candidate_daily=daily[1:],incumbent_daily=daily[1:],nav_csv='Date,Close\n2026-03-17,1\n')


if __name__ == '__main__': unittest.main()
