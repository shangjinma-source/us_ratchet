from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from backtest.current_quantity_v2_simulation_store import SimulationStore
from test_current_quantity_v2_simulated_settlement import fixture, run


class OperationInventoryTests(unittest.TestCase):
    def test_missing_database_is_not_created(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / 'missing.sqlite3'
            with self.assertRaisesRegex(ValueError, 'DATABASE_NOT_FOUND'):
                SimulationStore(path).inspect_operations('missing')
            self.assertFalse(path.exists())

    def test_restart_inventory_preserves_original_recovery_request(self):
        for phase in ('STARTED', 'FAILED', 'PREPARED'):
            with self.subTest(phase=phase), TemporaryDirectory() as folder:
                simulation, evidence, _ = fixture()
                path = Path(folder) / 'simulation.sqlite3'
                store = SimulationStore(path)
                initial = store.create(simulation)
                operation = dict(simulation_id=simulation['simulation_id'],
                    expected_revision=initial['revision'], operation_id='settle-one',
                    request=dict(kind='TEST_SETTLEMENT', evidence=evidence))
                if phase == 'PREPARED':
                    with patch.object(store, '_commit', side_effect=KeyboardInterrupt()):
                        with self.assertRaises(KeyboardInterrupt):
                            store.apply(**operation, transform=lambda state: run(state, evidence))
                else:
                    def fail(state):
                        if phase == 'STARTED':
                            raise KeyboardInterrupt()
                        raise ValueError('source unavailable')
                    with self.assertRaises(KeyboardInterrupt if phase == 'STARTED' else ValueError):
                        store.apply(**operation, transform=fail)
                before = sha256(path.read_bytes()).hexdigest()
                reopened = SimulationStore(path)
                inventory = reopened.inspect_operations(simulation['simulation_id'])
                self.assertEqual(before, sha256(path.read_bytes()).hexdigest())
                self.assertEqual(inventory['revision'], initial['revision'])
                saved = inventory['operations'][0]
                self.assertEqual(saved['status'], phase)
                self.assertEqual(saved['request'], operation['request'])
                self.assertEqual(saved['expected_revision'], initial['revision'])
                recovered_arguments = dict(simulation_id=inventory['simulation_id'],
                    expected_revision=saved['expected_revision'],
                    operation_id=saved['operation_id'], request=saved['request'])
                if phase == 'PREPARED':
                    result = reopened.recover(**recovered_arguments)
                    self.assertTrue(result['recovered'])
                    complete = reopened.inspect_operations(simulation['simulation_id'])
                    self.assertEqual(complete['operations'][0]['status'], 'COMPLETE')
                    self.assertEqual(complete['revision'], result['revision'])
                else:
                    with self.assertRaisesRegex(ValueError, 'PREPARED_RESULT_UNAVAILABLE'):
                        reopened.recover(**recovered_arguments)
                    self.assertEqual(reopened.read(simulation['simulation_id']), initial)


if __name__ == '__main__':
    unittest.main()
