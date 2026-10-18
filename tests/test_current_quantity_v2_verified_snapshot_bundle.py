from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from test_current_quantity_portfolio_research_v2 import fixture
from data.current_quantity_v2_verified_snapshot_bundle import VerifiedSnapshotBundleService


class VerifiedBundleTests(unittest.TestCase):
    def test_verified_bundle_one_load_detached_and_fresh_each_time(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);base,search,descriptor=fixture(root);service=VerifiedSnapshotBundleService(base);view=service.calculate('60')
            rid=view['research_id']
            with patch.object(base,'_load',wraps=base._load) as load:
                bundle=service.verified_snapshot_bundle(rid)
                self.assertEqual(load.call_count,1)
            self.assertEqual(bundle['source_hashes'],descriptor['source_hashes'])
            bundle['decision']['target_quantities'].clear();bundle['snapshot']['stocks'].clear()
            bundle['files']['B.json']=b'altered';bundle['source_hashes'].clear()
            fresh=service.verified_snapshot_bundle(rid)
            self.assertTrue(fresh['decision']['target_quantities']);self.assertTrue(fresh['snapshot']['stocks'])
            self.assertEqual(fresh['files']['B.json'],(root/'B.json').read_bytes())
            (root/'B.json').write_bytes(b'drift')
            with self.assertRaisesRegex(ValueError,'HASH_MISMATCH'):service.verified_snapshot_bundle(rid)
            self.assertEqual(search.call_count,1)

