from datetime import datetime
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
import test_build_real_monthly_release_entry as fixtures
from data.strategy_account_evidence_provider import REQUIRED_PINS
from scripts.build_real_monthly_release_entry import build
from data.strategy_paper_monthly_training_bridge_v2 import load_monthly_training


class PaperMonthlyTrainingBridgeTests(unittest.TestCase):
    def test_actual_monthly_producer_to_paper_training_without_activation(self):
        with TemporaryDirectory() as folder:
            fixture=fixtures.EntryTests();root,args=fixture.setup_package(folder)
            entry=build(**args)
            digest=fixture.save(root,'paper-training-registry.json',dict(schema='REAL_STRATEGY_MONTHLY_RELEASES_V1',entries=[entry]))
            pins={}
            for name in REQUIRED_PINS:
                raw=(Path(__file__).resolve().parents[1]/name).read_bytes()
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
                pins[name]=sha256(raw).hexdigest()
            before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            clock=lambda:datetime.fromisoformat('2026-12-01T15:00:00+00:00')
            with patch('socket.socket',side_effect=AssertionError('reader must not fetch')):
                loaded=load_monthly_training(root=root,registry_path='paper-training-registry.json',registry_sha256=digest,
                    runtime_pins=pins,output_root=root/'paper-selection',clock=clock)
                _,training=loaded['provider'].training()
            self.assertEqual(loaded['target_month'],'2026-12')
            # The existing producer fixture uses a shortened synthetic calendar.
            self.assertEqual(training['decision_date'],'2026-11-02')
            self.assertEqual(training['decision_date'],loaded['provider'].closed[:10])
            self.assertEqual(set(loaded['securities']),set(training['prices']))
            self.assertEqual(before,{p:p.read_bytes() for p in root.rglob('*') if p.is_file()})
            self.assertFalse((root/'data/strategy_account').exists())
            self.assertFalse((root/'paper-selection').exists())
            (root/loaded['training_reference']['path']).write_bytes(b'{}')
            with self.assertRaises(ValueError):
                load_monthly_training(root=root,registry_path='paper-training-registry.json',registry_sha256=digest,
                    runtime_pins=pins,output_root=root/'paper-selection',clock=clock)


if __name__=='__main__':unittest.main()
