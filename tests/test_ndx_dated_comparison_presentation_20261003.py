from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/ndx_dated_comparison_presentation_20261003.py'
SPEC = importlib.util.spec_from_file_location('presentation_publication', SCRIPT)
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


def fixture():
    references = {role: dict(path=role, sha256='a'*64) for role in m.BOUND}
    flags = {key: False for key in m.FALSE_FLAGS}
    summary = dict(schema='SOURCE_BOUND_DATED_COMPARISON_RESULTS_SUMMARY_V1', tables=dict(supplied_comparison_count=1632, not_supplied_count=0), source_hashes={}, **flags)
    publication = dict(schema='DATED_COMPARISON_RESULTS_SUMMARY_PUBLICATION_V1', status='PUBLISHED_SAVED_DIAGNOSTIC_TABLES', summary_reference=deepcopy(references['summary']), source_hashes={}, **flags)
    audit = dict(schema='DATED_COMPARISON_RESULTS_SUMMARY_INDEPENDENT_READBACK_V1', status='PASS', summary_reference=deepcopy(references['summary']), publication_reference=deepcopy(references['publication']), reader_sha256=references['reader']['sha256'], **flags)
    return summary, publication, audit, references


class Tests(unittest.TestCase):
    def test_pending_pins_reject_before_output(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(m, 'OUTPUT', Path(folder)/'new'), patch.dict(m.BOUND, {'summary': ('unused', None)}):
            with self.assertRaisesRegex(ValueError, 'pins pending'):
                m.run(execute=True)
            self.assertFalse(m.OUTPUT.exists())

    def test_exact_audit_and_complete_counts_required(self):
        arguments = fixture()
        before = deepcopy(arguments)
        self.assertEqual(m.validate(*arguments), arguments[0]['tables'])
        self.assertEqual(arguments, before)
        mutations = (
            lambda a: a[2]['summary_reference'].update(sha256='b'*64),
            lambda a: a[2].update(reader_sha256='b'*64),
            lambda a: a[1].update(source_hashes={'new': 'b'*64}),
            lambda a: a[0]['tables'].update(supplied_comparison_count=1631),
            lambda a: a[0]['tables'].update(not_supplied_count=False),
            lambda a: a[2].update(future_independent_oos=0),
        )
        for mutate in mutations:
            arguments = fixture()
            mutate(arguments)
            with self.assertRaises(ValueError):
                m.validate(*arguments)

    def test_postwrite_source_failure_preserved_and_namespace_not_retried(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            summary, publication, audit, references = fixture()
            reader = b'# synthetic reader source only\n'
            adapter = b'def build_tables(tables):\n return dict(tables=[],source_bytes_authenticated=False)\n'
            # Resolve hashes in dependency order, mirroring actual external pins.
            content = {'summary': m.encode(summary), 'reader': reader, 'adapter': adapter}
            for role in content:
                references[role] = dict(path=str(root/role), sha256=m.digest(content[role]))
            publication['summary_reference'] = deepcopy(references['summary'])
            content['publication'] = m.encode(publication)
            references['publication'] = dict(path=str(root/'publication'), sha256=m.digest(content['publication']))
            audit.update(summary_reference=deepcopy(references['summary']), publication_reference=deepcopy(references['publication']), reader_sha256=references['reader']['sha256'])
            content['audit'] = m.encode(audit)
            references['audit'] = dict(path=str(root/'audit'), sha256=m.digest(content['audit']))
            for role, blob in content.items():
                (root/role).write_bytes(blob)
            bound = {role: (ref['path'], ref['sha256']) for role, ref in references.items()}
            with patch.object(m, 'BOUND', bound), patch.object(m, 'OUTPUT', root/'output'), patch.object(m, 'guard', side_effect=[None, ValueError('changed')]):
                with self.assertRaisesRegex(ValueError, 'changed'):
                    m.run(execute=True)
                self.assertEqual({p.name for p in m.OUTPUT.iterdir()}, {'started.json', 'presentation.json', 'failure.json'})
                self.assertFalse(json.loads((m.OUTPUT/'failure.json').read_bytes())['retry_allowed'])
                with self.assertRaisesRegex(ValueError, 'namespace exists'):
                    m.run(execute=True)


if __name__ == '__main__':
    unittest.main()
