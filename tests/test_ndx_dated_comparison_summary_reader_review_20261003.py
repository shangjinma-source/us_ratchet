"""Independent synthetic projection, missing-value and source closure checks."""
from copy import deepcopy
import ast
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts import ndx_dated_comparison_results_summary_independent_readback_20261003 as reader
from test_ndx_dated_comparison_results_summary_independent_readback_20261003 import case


class Review(unittest.TestCase):
    def test_independently_pinned_base_and_exact_union(self):
        bound = {name: (path, digest or 'b'*64) for name, (path, digest) in reader.BOUND.items()}
        pins = {name: (path, digest or 'c'*64) for name, (path, digest) in reader.READERS.items()}
        with patch.object(reader, 'BOUND', bound), patch.object(reader, 'READERS', pins):
            base = reader.expected_producer_sources()
        self.assertEqual(len(base), 12)
        self.assertEqual(base[str(reader.CORE)], reader.CORE_SHA)
        for path, digest in pins.values():
            self.assertEqual(base[str(reader.ROOT/path)], digest)
        union = {**base, 'synthetic comparison': 'd'*64}
        docs = [{'source_hashes': deepcopy(base)}, {'source_hashes': deepcopy(union)}, {'source_hashes': deepcopy(union)}]
        reader.verify_source_tables(*docs, base, union)
        for mutate in (
            lambda d: d[0].update(source_hashes={}),
            lambda d: d[0]['source_hashes'].pop(str(reader.CORE)),
            lambda d: d[1]['source_hashes'].update(invented='e'*64),
            lambda d: d[2]['source_hashes'].pop('synthetic comparison'),
        ):
            bad = deepcopy(docs); mutate(bad)
            with self.assertRaises(ValueError):
                reader.verify_source_tables(*bad, base, union)

    def test_saved_fields_direction_weights_and_absence_preserved_without_recompute(self):
        args, tables = case()
        task = args['task_summary']['rows'][2]
        saved = args['comparisons_by_task'][task['numerical_task_id']]
        document = saved['document']
        row = tables['rows'][2]
        for i, mode in enumerate(reader.MODES):
            value = {'exact': '-3/17' if i == 0 else '5/19', 'decimal': 'saved diagnostic'}
            document['comparison']['absolute_distance_comparisons'][mode]['integer']['annualized_return']['candidate_minus_incumbent_distance'] = deepcopy(value)
            row['nav_modes'][mode]['absolute_distance_comparisons']['integer']['annualized_return']['candidate_minus_incumbent_distance'] = deepcopy(value)
        document['comparison']['tracks']['candidate_continuous']['original_track_preserved']['positions_preserved'][0]['target_weight'] = .25000000000000006
        row['original_targets'][0]['target_weight'] = .25000000000000006
        before = deepcopy((args, tables))
        refs = dict(comparison_reference=saved['document_reference'], independent_readback_reference=saved['audit_reference'])
        reader.verify_row(row, task, document, saved['audit'], refs)
        self.assertEqual((args, tables), before)
        self.assertIsNone(tables['rows'][1]['tracks']['candidate_integer']['metrics'])
        self.assertEqual(row['tracks']['candidate_integer']['decision_status'], 'NO_PLAN')
        self.assertEqual(row['tracks']['candidate_integer']['execution_statuses'], [])

    def test_projection_alterations_and_stratum_scope_rejected(self):
        for mutate in (
            lambda r: r.update(target_weights_normalized_by_summary=True),
            lambda r: r['tracks']['candidate_integer'].update(execution_statuses=['REJECTED']),
            lambda r: r['nav_modes'][reader.MODES[0]]['nav_source_reference'].update(path='other'),
            lambda r: r['source_references_preserved'].update(extra='invented'),
        ):
            args, tables = case()
            task = args['task_summary']['rows'][2]
            saved = args['comparisons_by_task'][task['numerical_task_id']]
            row = deepcopy(tables['rows'][2]); mutate(row)
            with self.assertRaises(ValueError):
                reader.verify_row(row, task, saved['document'], saved['audit'],
                    dict(comparison_reference=saved['document_reference'], independent_readback_reference=saved['audit_reference']))
        args, tables = case()
        tables['k_spec_coverage'][0]['candidate_integer_status_counts']['AVAILABLE'] = 99
        with self.assertRaises(ValueError):
            reader.verify_tables(tables, args['task_summary'], args['comparisons_by_task'])

    def test_reader_does_not_import_or_invoke_projection_producer(self):
        tree = ast.parse(Path(reader.__file__).read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = ([node.module or ''] if isinstance(node, ast.ImportFrom) else [item.name for item in node.names])
                self.assertFalse(any('ndx_' in name for name in names))
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                self.assertNotIn(node.func.id, ('exec', 'compile', '__import__'))


if __name__ == '__main__':
    unittest.main()
