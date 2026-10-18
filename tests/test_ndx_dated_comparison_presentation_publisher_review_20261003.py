"""Source-bound publisher tests in temporary directories; no actual display output."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import ndx_dated_comparison_presentation_20261003 as module
from test_ndx_dated_comparison_presentation_20261003 import fixture
from test_ndx_dated_comparison_presentation_research import source


def files(root, full=False):
    summary, publication, audit, references = fixture()
    if full:
        tables = source()
        template = deepcopy(tables['rows'][2])
        missing = deepcopy(tables['rows'][1])
        for index, task in enumerate(tables['rows']):
            row = deepcopy(missing if index == 0 else template)
            row.update(numerical_task_id=task['numerical_task_id'], k=task['k'], weight_spec=task['weight_spec'])
            row['original_targets'] = [dict(ticker='T'+str(i), security_id='S'+str(i), issuer_id='I'+str(i),
                target_weight=0.0 if index == i == 0 else 0.25000000000000006) for i in range(task['k'])]
            tables['rows'][index] = row
        tables.update(supplied_comparison_count=1632, not_supplied_count=0)
        summary['tables'] = tables
        adapter = (module.ROOT/module.BOUND['adapter'][0]).read_bytes()
    else:
        adapter = b'def build_tables(tables):\n return dict(tables=[], source_bytes_authenticated=False)\n'
    content = dict(summary=module.encode(summary), reader=b'# synthetic reader bytes\n', adapter=adapter)
    for role, blob in content.items():
        references[role] = dict(path=str(root/role), sha256=module.digest(blob))
    publication['summary_reference'] = deepcopy(references['summary'])
    content['publication'] = module.encode(publication)
    references['publication'] = dict(path=str(root/'publication'), sha256=module.digest(content['publication']))
    audit.update(summary_reference=deepcopy(references['summary']), publication_reference=deepcopy(references['publication']), reader_sha256=references['reader']['sha256'])
    content['audit'] = module.encode(audit)
    references['audit'] = dict(path=str(root/'audit'), sha256=module.digest(content['audit']))
    for role, blob in content.items():
        (root/role).write_bytes(blob)
    return {role: (reference['path'], reference['sha256']) for role, reference in references.items()}


class Review(unittest.TestCase):
    def test_full_delivery_six_tables_with_missing_integer_and_original_weights(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bound = files(root, full=True)
            original = (root/'summary').read_bytes()
            with patch.object(module, 'BOUND', bound), patch.object(module, 'OUTPUT', root/'output'):
                reference = module.run(execute=True)
            result = json.loads(Path(reference['path']).read_bytes())
            self.assertEqual((root/'summary').read_bytes(), original)
            tables = {table['name']: table['rows'] for table in result['display']['tables']}
            self.assertEqual(len(tables), 6)
            self.assertEqual(len(tables['全部任务']), 1632)
            self.assertEqual(len(tables['四轨指标']), 1632*4)
            self.assertEqual(len(tables['双基准距离']), 1632*8)
            self.assertEqual(tables['四轨指标'][0][-3:], [None, None, None])
            self.assertEqual(tables['原始目标权重'][0][-1], 0.0)
            self.assertEqual(tables['原始目标权重'][1][-1], 0.25000000000000006)
            self.assertEqual(len(tables['来源索引']), 5)
            self.assertIs(result['display']['source_bytes_authenticated'], False)
            self.assertIs(result['workbook_created'], False)
            self.assertEqual({p.name for p in (root/'output').iterdir()}, {'started.json', 'presentation.json', 'publication.json'})

    def test_pending_and_wrong_direct_bytes_fail_before_namespace(self):
        with patch.dict(module.BOUND, {'summary': ('pending', None)}), patch.object(Path, 'read_bytes') as read:
            with self.assertRaises(ValueError):
                module.run(execute=True)
            read.assert_not_called()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bound = files(root)
            (root/'reader').write_bytes(b'changed reader')
            with patch.object(module, 'BOUND', bound), patch.object(module, 'OUTPUT', root/'output'):
                with self.assertRaises(ValueError):
                    module.run(execute=True)
            self.assertFalse((root/'output').exists())

    def test_postpublication_drift_keeps_receipt_and_failure_no_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bound = files(root)
            with patch.object(module, 'BOUND', bound), patch.object(module, 'OUTPUT', root/'output'), \
                    patch.object(module, 'guard', side_effect=[None, None, ValueError('Post-receipt drift')]):
                with self.assertRaises(ValueError):
                    module.run(execute=True)
                self.assertEqual({p.name for p in module.OUTPUT.iterdir()}, {'started.json', 'presentation.json', 'publication.json', 'failure.json'})
                with self.assertRaises(ValueError):
                    module.run(execute=True)


if __name__ == '__main__':
    unittest.main()
