"""Versioned source bridge retains existing accounting and failure coverage."""
from pathlib import Path
from types import ModuleType
import copy
import unittest
from unittest.mock import patch

from scripts import ndx_cash_neighbor_combined_selected_paths_20261008 as producer

ROOT = Path(__file__).resolve().parents[1]


class CombinedSourceContractTests(unittest.TestCase):
    def test_exact_combined_parent_roles_and_full_domain(self):
        references = {role: dict(path=role, sha256='a' * 64) for role in ('selection', 'selection_publication', 'selection_audit', 'selection_reader', 'paired', 'paired_publication', 'preparation')}
        cases = [dict(scenario_index=i, scenario_id=f'scenario-{i}', status='NO_FEASIBLE_CANDIDATE') for i in range(40)]
        common = dict(scenario_count=40, total_candidate_count=304305, cases=cases, risk_recomputed=False, account_executed=False, point_in_time_verified=False, promotion_allowed=False)
        index = dict(common, schema='CASH_NEIGHBOR_COMBINED_STREAM_SELECTION_INDEX_V1', status='COMPLETE_DECLARED_UNION_SELECTION', source_hashes={}, input_references={role: references[role] for role in ('paired', 'paired_publication', 'preparation')})
        publication = dict(schema='CASH_NEIGHBOR_COMBINED_STREAM_SELECTION_PUBLICATION_V1', status='PUBLISHED_COMPLETE_DECLARED_UNION_SELECTION', index_reference=references['selection'], source_hashes={})
        audit = dict(common, schema='CASH_NEIGHBOR_COMBINED_SELECTION_INDEPENDENT_READBACK_V1', status='PASS', index_reference=references['selection'], publication_reference=references['selection_publication'], reader_sha256=references['selection_reader']['sha256'], complete_saved_score_order_independently_verified=True)
        documents = dict(selection=index, selection_publication=publication, selection_audit=audit, preparation=dict(rows=cases), paired_publication=dict(account_reference=references['paired']))
        self.assertEqual(len(producer.validate_parents(documents, references)), 40)
        for role, old_schema in [('selection', 'CASH_NEIGHBOR_STREAM_SELECTION_INDEX_V1'), ('selection_publication', 'CASH_NEIGHBOR_STREAM_SELECTION_PUBLICATION_V1'), ('selection_audit', 'CASH_NEIGHBOR_SELECTION_INDEPENDENT_READBACK_V1')]:
            bad = copy.deepcopy(documents)
            bad[role]['schema'] = old_schema
            with self.assertRaises(ValueError):
                producer.validate_parents(bad, references)
        for role in ('selection', 'selection_audit'):
            bad = copy.deepcopy(documents)
            bad[role]['total_candidate_count'] -= 1
            with self.assertRaises(ValueError):
                producer.validate_parents(bad, references)


def load_tests(loader, standard_tests, pattern):
    suite = unittest.TestSuite([standard_tests])
    names = (
        'test_ndx_cash_neighbor_selected_paths_20261003.py',
        'test_ndx_cash_neighbor_selected_paths_independent_readback_20261003.py',
        'test_ndx_cash_selected_paths_wrapper_review_20261003.py',
        'test_ndx_cash_selected_paths_reader_review_20261003.py',
    )
    for index, name in enumerate(names):
        path = ROOT / 'tests' / name
        source = path.read_text(encoding='utf-8')
        source = source.replace('from scripts import ndx_cash_neighbor_selected_paths_20261003 as m', 'from scripts import ndx_cash_neighbor_combined_selected_paths_20261008 as m')
        source = source.replace('from scripts import ndx_cash_neighbor_selected_paths_independent_readback_20261003 as m', 'from scripts import ndx_cash_neighbor_combined_selected_paths_independent_readback_20261008 as m')
        module = ModuleType(f'combined_selected_paths_inherited_{index}')
        module.__file__ = str(path)
        exec(compile(source, str(path), 'exec'), module.__dict__)
        pending_cases = {
            0: ('Tests', 'test_pending_before_io', 'selection'),
            1: ('Tests', 'test_pending_before_filesystem', 'result'),
            3: ('IndependentReview', 'test_partition_no_invented_completion_and_pending_before_io', 'result'),
        }
        if index in pending_cases:
            class_name, method_name, role = pending_cases[index]
            test_class = getattr(module, class_name)
            original_pending = getattr(test_class, method_name)
            def pending_with_explicit_anchor(self, original=original_pending, subject=module.m, role=role):
                # Pending is an explicit fixture, independent of later real binding.
                path, _ = subject.BOUND[role]
                with patch.dict(subject.BOUND, {role: (path, None)}):
                    original(self)
            setattr(test_class, method_name, pending_with_explicit_anchor)
        suite.addTests(loader.loadTestsFromModule(module))
    return suite


if __name__ == '__main__':
    unittest.main()
