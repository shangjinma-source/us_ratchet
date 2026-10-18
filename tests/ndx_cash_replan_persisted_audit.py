"""Independent arithmetic and recovery-lineage audit; no simulator imports."""
import json
from pathlib import Path

from test_ndx_v3_recheck_persisted_economics import PersistedEconomicsTests, REPORT_ROOT


def audit_replan(report_path, digest):
    report_path = Path(report_path).resolve()
    checks = PersistedEconomicsTests()
    report = json.loads(checks.read_bound(report_path, digest))
    case_index = report['case_index']
    baseline_reference = report['baseline_reference']
    baseline_report = json.loads(checks.read_bound(baseline_reference['path'], baseline_reference['sha256']))

    class BoundReplanEconomics(PersistedEconomicsTests):
        def read_bound(self, path, expected):
            if Path(path) == REPORT_ROOT / f'v3_same_execution_case{case_index}_20260911.json':
                path = report_path
            return super().read_bound(path, expected)

    BoundReplanEconomics().audit(case_index, digest)
    summary = {}
    for role in ('candidate', 'incumbent'):
        path = report[role]
        checks.assertEqual(path['recovery_policy'], 'ONE_REPLAN_AFTER_CASH_REJECTION')
        decisions = path['decisions']
        lineage = path['decision_lineage']
        checks.assertEqual(len(decisions), len(lineage))
        checks.assertEqual(len(path['executions']), len(path['execution_lineage']))
        by_date = {row['decision_date']: row for row in decisions}
        origins = {row['decision_date']: row for row in lineage}
        checks.assertEqual(len(by_date), len(decisions))
        checks.assertEqual(len(origins), len(lineage))
        original_dates = {row['decision_date'] for row in lineage if row['decision_kind'] == 'ORIGINAL_SCHEDULE'}
        checks.assertEqual([(row['decision_date'], row['target_weights']) for row in decisions
                            if row['decision_date'] in original_dates],
                           [(row['decision_date'], row['target_weights'])
                            for row in baseline_report[role]['decisions']])
        executions = {row['execution_date']: row for row in path['executions']}
        recovery_parents = set()
        recovery_count = 0
        for decision, origin in zip(decisions, lineage):
            date, parent = decision['decision_date'], origin['parent_decision_id']
            checks.assertEqual(origin['decision_date'], date)
            if origin['decision_kind'] == 'ORIGINAL_SCHEDULE':
                checks.assertEqual(parent, date)
                continue
            checks.assertEqual(origin['decision_kind'], 'ONE_REPLAN_AFTER_CASH_REJECTION')
            checks.assertNotIn(parent, recovery_parents)
            recovery_parents.add(parent)
            recovery_count += 1
            checks.assertIn(parent, original_dates)
            checks.assertNotIn(date, original_dates)
            checks.assertEqual(decision['target_weights'], by_date[parent]['target_weights'])
            trigger = executions[date]
            checks.assertEqual(trigger['status'], 'REJECTED_INSUFFICIENT_CASH_AT_FILL')
            checks.assertEqual(trigger['decision_date'], parent)
            checks.assertEqual(report['calendar'].index(date), report['calendar'].index(parent) + 1)
        for execution, origin in zip(path['executions'], path['execution_lineage']):
            checks.assertEqual(origin, dict(execution_date=execution['execution_date'],
                                            **origins[execution['decision_date']]))
        checks.assertEqual(recovery_count, path['supplemental_decision_count'])
        if path['pending_plan'] is not None:
            pending = path['pending_plan']
            checks.assertEqual(pending['decision_date'], report['calendar'][-1])
            checks.assertEqual(pending['status'], 'PENDING_OUTSIDE_EVALUATION')
            checks.assertIsNone(pending['expected_execution_date'])
            checks.assertEqual(path['pending_lineage'], origins[pending['decision_date']])
        else:
            checks.assertIsNone(path['pending_lineage'])
        summary[role] = dict(daily_rows=len(path['daily']), executions=len(path['executions']),
                            decisions=len(decisions), independently_verified_recoveries=recovery_count)
    return dict(report_path=str(report_path), sha256=digest,
                arithmetic_and_lineage_verified=True, summary=summary,
                market_data_authenticity_verified=False, optimality_verified=False)
