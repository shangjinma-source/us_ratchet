"""Physical source closure and publication drift checks; no account execution."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, main
from unittest.mock import patch

from scripts import ndx_multidecision_account_inputs_20261003 as publisher
from test_ndx_multidecision_account_inputs_20261003 import physical_sources


class SourceClosureTests(TestCase):
    def test_underlying_price_bytes_and_added_parent_file_fail_after_publication(self):
        for mutation in ('price_bytes', 'parent_inventory'):
            with self.subTest(mutation=mutation), TemporaryDirectory() as directory:
                root = Path(directory)
                outer, reader, bindings = physical_sources(root)
                output = root / 'output'
                original_save = publisher.save

                def save_with_drift(name, value, emergency=False):
                    reference = original_save(name, value, emergency=emergency)
                    if name == 'publication.json':
                        if mutation == 'price_bytes':
                            (root / 'prices/raw0').write_bytes(b'changed source')
                        else:
                            (outer / 'unexpected.json').write_bytes(b'{}')
                    return reference

                with patch.object(publisher, 'ROOT', root), patch.object(publisher, 'OUTER_ROOT', outer), patch.object(publisher, 'OUTER_READER', Path(reader['path'])), patch.object(publisher, 'BOUND', bindings), patch.object(publisher, 'OUTPUT', output), patch.object(publisher, 'resource'), patch.object(publisher, 'save', side_effect=save_with_drift):
                    expected = 'Source drift' if mutation == 'price_bytes' else 'inventory drift'
                    with self.assertRaisesRegex(ValueError, expected):
                        publisher.run(execute=True)
                    self.assertTrue((output / 'failure.json').exists())
                    document = publisher.decode((output / 'inputs.json').read_bytes())
                    self.assertEqual(document['inputs']['coordinate_count'], 48)
                    self.assertFalse(document['account_simulation_performed'])
                    self.assertTrue((output / 'publication.json').exists())
                    with self.assertRaisesRegex(ValueError, 'Create only'):
                        publisher.run(execute=True)


if __name__ == '__main__':
    main()
