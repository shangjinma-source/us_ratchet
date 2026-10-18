import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts import ndx_standard_cash_scenarios_20261002 as module


def fixture():
    rows = [{'lane': f'lane{lane}', 'decision_date': f'2023-{month:02d}-01',
             'execution_date': f'2023-{month:02d}-02', 'cash_event_amount_usd': None,
             'fork_executable': False, 'gaps': ['unresolved']}
            for lane in range(6) for month in range(1, 7)]
    return {'schema': 'CONDITIONAL_NEW_CASH_SIX_COORDINATE_INVENTORY_V2',
            'branch_coordinate_count': 36, 'rows': rows, 'cash_fork_called': False,
            'point_in_time_verified': False, 'promotion_allowed': False}


class ScenarioTests(unittest.TestCase):
    def test_each_parent_has_two_explicit_hypotheses_without_mutation(self):
        parent = fixture(); original = copy.deepcopy(parent)
        result = module.assemble(parent, {'path': 'fixture', 'sha256': 'a' * 64})
        self.assertEqual(parent, original)
        self.assertEqual(len({row['scenario_id'] for row in result['rows']}), 72)
        for index in range(36):
            pair = result['rows'][2 * index:2 * index + 2]
            self.assertEqual([row['standardized_cash_injection_usd'] for row in pair], ['1000', '10000'])
            self.assertTrue(all(row['parent_row_reference']['json_pointer'] == f'/rows/{index}' for row in pair))
            self.assertTrue(all(row['parent_gap_count'] == 1 and row['fork_executable'] is False for row in pair))
        self.assertFalse(result['actual_cash_event_registered'])

    def test_duplicate_existing_cash_and_authority_rejected(self):
        for attack in ('duplicate', 'cash', 'authority', 'date'):
            parent = fixture()
            if attack == 'duplicate': parent['rows'][1] = copy.deepcopy(parent['rows'][0])
            elif attack == 'cash': parent['rows'][0]['cash_event_amount_usd'] = '1000'
            elif attack == 'authority': parent['promotion_allowed'] = True
            else: parent['rows'][0]['execution_date'] = parent['rows'][0]['decision_date']
            with self.subTest(attack=attack), self.assertRaises(ValueError):
                module.assemble(parent, {})

    def test_existing_namespace_is_rejected_before_read(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(module, 'OUTPUT', Path(directory)), patch.object(module, 'PARENT') as parent:
            with self.assertRaises(ValueError): module.publish()
            parent.read_bytes.assert_not_called()

    def test_changed_loaded_code_rejected_before_parent_read(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(module, 'OUTPUT', Path(directory) / 'new'), patch.object(module, 'LOADED_SOURCE_SHA', '0' * 64), patch.object(module, 'PARENT') as parent:
            with self.assertRaisesRegex(ValueError, 'Loaded source changed'):
                module.publish()
            parent.read_bytes.assert_not_called()
