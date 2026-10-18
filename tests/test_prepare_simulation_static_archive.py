from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
from scripts.prepare_simulation_static_archive import prepare
from test_bootstrap_current_quantity_v2_simulation import fixture,NOW


class StaticPreparationTests(unittest.TestCase):
    def test_prepare_reuse_and_no_capture_or_account(self):
        with TemporaryDirectory() as folder:
            config,args=fixture(Path(folder))
            with patch('urllib.request.urlopen',side_effect=AssertionError('No network')):
                first=prepare(**args,now=NOW);second=prepare(**args,now=NOW)
            self.assertGreater(first['created'],0);self.assertEqual(second['created'],0)
            self.assertEqual(second['reused'],second['files'])
            self.assertFalse(Path(config['database_path']).exists())
            self.assertFalse(Path(config['pullback']['database_path']).exists())
            self.assertEqual([p.name for p in Path(config['audit_directory']).iterdir()],['blobs'])
            blob=next((Path(config['audit_directory'])/'blobs').iterdir());blob.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'OBSERVATION_CREATE_ONLY_CONFLICT'):prepare(**args,now=NOW)
            self.assertEqual(blob.read_bytes(),b'changed')


if __name__=='__main__':unittest.main()
