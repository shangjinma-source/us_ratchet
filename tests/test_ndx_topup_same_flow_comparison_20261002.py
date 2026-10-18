import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import ndx_topup_same_flow_comparison_20261002 as module


def fixture(root):
    docs, refs, pins = {}, {}, {}
    contracts = [('paired', 'OLD_HOLDING_TOPUP_PAIRED_ACCOUNT_PUBLICATION_V1', 'PUBLISHED_CONDITIONAL_PRICE_ONLY_PAIRED_PATHS'),
                 ('incumbent', 'INCUMBENT_CASH_FLOW_PATHS_PUBLICATION_V1', 'PUBLISHED_CONDITIONAL_SAME_FLOW_INCUMBENT_PATHS')]
    for prefix, schema, status in contracts:
        directory = root / prefix
        directory.mkdir()
        (directory / 'started.json').write_text('{}')
        role = prefix + '_accounts'
        docs[role] = {'source_hashes': {'saved-parent': 'a' * 64}, **module.FLAGS}
        raw = json.dumps(docs[role]).encode()
        path = directory / 'accounts.json'
        path.write_bytes(raw)
        refs[role] = {'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest()}
        pubrole = prefix + '_publication'
        docs[pubrole] = {'schema': schema, 'status': status, 'account_reference': refs[role],
                         'source_hashes': docs[role]['source_hashes'], **module.FLAGS}
        raw = json.dumps(docs[pubrole]).encode()
        path = directory / 'publication.json'
        path.write_bytes(raw)
        refs[pubrole] = {'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest()}
    for role, ref in refs.items():
        pins[role] = (ref['path'], ref['sha256'])
    for role in ('core', 'metrics'):
        path = root / (role + '.py')
        path.write_text('# synthetic dependency')
        pins[role] = (str(path), module.sha(path.read_bytes()))
    return docs, refs, pins


class Tests(unittest.TestCase):
    def test_publication_and_failed_namespace(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            docs, refs, _ = fixture(root)
            module.validate_publications(docs, refs)
            docs['paired_publication']['point_in_time_verified'] = True
            with self.assertRaises(ValueError): module.validate_publications(docs, refs)
            docs['paired_publication']['point_in_time_verified'] = False
            (root / 'paired' / 'failure.json').write_text('{}')
            with self.assertRaises(ValueError): module.validate_publications(docs, refs)

    def test_receipt_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            docs, refs, _ = fixture(Path(directory))
            docs['incumbent_publication']['account_reference'] = dict(refs['paired_accounts'])
            with self.assertRaises(ValueError): module.validate_publications(docs, refs)

    def test_pending_and_no_retry_before_load(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(module, 'OUTPUT', Path(directory) / 'output'):
            with patch.object(module, 'PINS', {'core': ('unused', None)}), patch.object(module, 'load_compare') as load:
                with self.assertRaises(ValueError): module.run()
                load.assert_not_called()
                module.OUTPUT.mkdir()
                with self.assertRaisesRegex(ValueError, 'no retry'): module.run()

    def test_synthetic_single_compare_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, _, pins = fixture(root)
            result = {'schema': 'TOPUP_SAME_FLOW_INCUMBENT_EXACT_COMPARISON_V1', 'rows': [{} for _ in range(40)], **module.FLAGS}
            with patch.object(module, 'PINS', pins), patch.object(module, 'OUTPUT', root / 'output'), \
                    patch.object(module, 'load_compare', return_value=lambda **kwargs: result):
                publication = module.run()
                self.assertEqual(module.sha(Path(publication['path']).read_bytes()), publication['sha256'])
                with self.assertRaisesRegex(ValueError, 'no retry'): module.run()

    def test_post_publication_source_drift_leaves_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, _, pins = fixture(root)
            result = {'schema': 'TOPUP_SAME_FLOW_INCUMBENT_EXACT_COMPARISON_V1', 'rows': [{} for _ in range(40)], **module.FLAGS}
            original = module.write_new
            def write(path, value):
                digest = original(path, value)
                if path.name == 'publication.json': Path(pins['metrics'][0]).write_text('# changed')
                return digest
            with patch.object(module, 'PINS', pins), patch.object(module, 'OUTPUT', root / 'output'), \
                    patch.object(module, 'load_compare', return_value=lambda **kwargs: result), patch.object(module, 'write_new', write):
                with self.assertRaisesRegex(ValueError, 'Source drift'): module.run()
                self.assertTrue((module.OUTPUT / 'failure.json').exists())


if __name__ == '__main__': unittest.main()
