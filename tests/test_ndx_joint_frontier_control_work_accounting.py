"""Two small work-accounting regressions against frozen pre-delta bytes."""
from copy import deepcopy
import hashlib
import importlib.util
from pathlib import Path
import types
import unittest
from unittest.mock import patch

from backtest import ndx_joint_new_cash_competition_frontier_research as current

_author_spec = importlib.util.spec_from_file_location('frozen_author_fixture_only',
    Path(__file__).with_name('test_ndx_joint_new_cash_competition_frontier_research.py'))
_author_fixture = importlib.util.module_from_spec(_author_spec)
_author_spec.loader.exec_module(_author_fixture)
case, prepare = _author_fixture.case, _author_fixture.prepare


ORIGINAL = Path(__file__).resolve().parents[1] / 'tmp/joint_frontier_control_work_accounting_author_20261009_v1/original_module.py'
ORIGINAL_SHA = '08a7c6018fc170005b0c205c5c07b0a000fd07696717be66ba75dcd55240e217'
ADDED_FIELDS = {'control_audit_classifications', 'total_classification_calls', 'work_budget_scope'}


def original_module():
    source = ORIGINAL.read_bytes()
    if hashlib.sha256(source).hexdigest() != ORIGINAL_SHA:
        raise ValueError('Frozen pre-delta module drift')
    module = types.ModuleType('frozen_joint_frontier_accounting_reference')
    exec(compile(source, str(ORIGINAL), 'exec'), module.__dict__)
    return module


class ControlAccountingTests(unittest.TestCase):
    def setUp(self):
        self.original = original_module()
        self.competition = prepare(case(('A', 'B')))

    def compare(self, budget, resume=None, expected=None):
        kwargs = dict(competition=self.competition, work_budget=budget,
                      resume_state=resume, expected_resume_sha256=expected)
        with patch.object(current, '_classify', wraps=current._classify) as counted:
            result = current.run_synthetic_joint_frontier(**kwargs)
        before = self.original.run_synthetic_joint_frontier(**kwargs)
        inverse = deepcopy(result)
        coverage = inverse['coverage']
        self.assertEqual(set(coverage)-set(before['coverage']), ADDED_FIELDS)
        for name in ADDED_FIELDS:
            del coverage[name]
        self.assertEqual(inverse, before)
        work = result['coverage']
        self.assertEqual(work['control_audit_classifications'], 1)
        self.assertEqual(work['total_classification_calls'], counted.call_count)
        self.assertEqual(work['total_classification_calls'],
                         work['newly_classified_tuples']+work['resume_prefix_validation_tuples']+1)
        self.assertEqual(work['work_budget_scope'],
                         'NEW_SEARCH_TUPLES_ONLY_EXCLUDES_REPLAY_AND_CONTROL_AUDIT')
        return result

    def test_zero_budget_still_audits_control_once_without_search_progress(self):
        result = self.compare(0)
        self.assertEqual(result['coverage']['total_classification_calls'], 1)
        self.assertEqual(result['coverage']['newly_classified_tuples'], 0)
        self.assertEqual(result['resume_state']['cursor'], 0)
        self.assertEqual(result['status'], 'BUDGET_STOPPED')
        self.assertIsNotNone(result['zero_buy_control'])

    def test_resume_replays_prefix_and_repeats_control_once_per_call(self):
        first = self.compare(2)
        second = self.compare(1, first['resume_state'], first['resume_sha256'])
        self.assertEqual(second['coverage']['newly_classified_tuples'], 1)
        self.assertEqual(second['coverage']['resume_prefix_validation_tuples'], 2)
        self.assertEqual(second['coverage']['total_classification_calls'], 4)
        stopped = self.compare(0, second['resume_state'], second['resume_sha256'])
        self.assertEqual(stopped['coverage']['newly_classified_tuples'], 0)
        self.assertEqual(stopped['coverage']['resume_prefix_validation_tuples'], 3)
        self.assertEqual(stopped['coverage']['total_classification_calls'], 4)
        self.assertEqual(stopped['resume_state'], second['resume_state'])


if __name__ == '__main__':
    unittest.main()
