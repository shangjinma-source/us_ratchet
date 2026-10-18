"""Read-only compatibility and rejection tests using the already sealed K bytes."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest

from backtest import ndx_multidecision_path_presentation_research as subject

ROOT = Path(__file__).resolve().parents[1]


def fixture():
    specifications = {
        'comparison': ('data/cache/research/multidecision_path_comparison_20261003_v1/comparison.json', '40e32bbea680775252bcdc880c5ca07cc7163ed5e0af42707ac8c56a009e1656'),
        'publication': ('data/cache/research/multidecision_path_comparison_20261003_v1/publication.json', 'bdbb1abdff6253227b73329b4a3a7081f98a12fb180d6bbd06724a2798f4430e'),
        'audit': ('data/cache/research/multidecision_path_comparison_independent_readback_20261003_v1/independent_readback.json', '4d50cc9f2d8be07697242363849cc2d051a984dca55f3d325d201f11da942fd2'),
        'reader': ('scripts/ndx_multidecision_path_comparison_independent_readback_20261003.py', 'bc3e4f8b70c7cc01b04089f7c43d9ba7aae511159747bfb47ce6b5e4996fc4d7'),
        'candidate_inputs': ('data/cache/research/multidecision_account_inputs_20261003_v1/inputs.json', 'c3311e2e9aea24c96c695e5a860f6ecd784356bbc8995657f1e13061de0ff4b9'),
    }
    documents, references = {}, {}
    for role, (name, checksum) in specifications.items():
        path = ROOT / name
        blob = path.read_bytes()
        assert hashlib.sha256(blob).hexdigest() == checksum
        references[role] = dict(path=str(path), sha256=checksum)
        if role != 'reader':
            documents[role] = json.loads(blob)
    return dict(comparison_document=documents['comparison'], publication=documents['publication'], audit=documents['audit'], candidate_inputs_document=documents['candidate_inputs'], references=references)


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = fixture()

    def test_sealed_full_domain_projection_no_mutation(self):
        arguments = deepcopy(self.original)
        before = subject.encoded(arguments)
        result = subject.build_tables(**arguments)
        self.assertEqual(subject.encoded(arguments), before)
        self.assertEqual(result['original_comparison_preserved'], arguments['comparison_document']['comparison'])
        self.assertEqual(result['original_coordinates_preserved'], arguments['candidate_inputs_document']['inputs']['outer_coordinate_rows_preserved'])
        tables = {table['name']: table for table in result['tables']}
        self.assertEqual([len(tables[name]['rows']) for name in ('轨道与阻断', '已存路径指标', '到NAV的逐项距离', '两种NAV参考', '48个决策位置', '已存归一轨迹')], [16, 32, 16, 2, 48, 3120])
        self.assertTrue(all(row[-3:] == [None]*3 for row in tables['已存路径指标']['rows'][:16:2]))
        for row in tables['已存路径指标']['rows'][16::2]:
            self.assertIsInstance(row[-2], str)
        self.assertFalse(result['source_bytes_authenticated'])
        self.assertFalse(result['financial_recomputation_performed'])

    def test_truncation_reorder_and_boolean_counts_rejected(self):
        for mutation in ('truncate', 'reorder', 'boolcount', 'coordinate', 'curve'):
            with self.subTest(mutation=mutation):
                args = deepcopy(self.original)
                comp = args['comparison_document']['comparison']
                if mutation == 'truncate': comp['rows'].pop()
                elif mutation == 'reorder': comp['rows'][0], comp['rows'][1] = comp['rows'][1], comp['rows'][0]
                elif mutation == 'boolcount': comp['coordinate_count'] = True
                elif mutation == 'coordinate': args['candidate_inputs_document']['inputs']['outer_coordinate_rows_preserved'][0]['coordinate_index'] = False
                else: comp['rows'][-1]['candidate']['metrics']['wealth'].pop()
                with self.assertRaises(ValueError): subject.build_tables(**args)

    def test_bad_audit_authority_binding_and_blockers_rejected(self):
        for mutation in ('audit', 'authority', 'binding', 'blocker', 'fakeblockedmetric', 'mode'):
            with self.subTest(mutation=mutation):
                args = deepcopy(self.original)
                comp = args['comparison_document']['comparison']
                if mutation == 'audit': args['audit']['status'] = 'FAILED'
                elif mutation == 'authority': comp['promotion_allowed'] = True
                elif mutation == 'binding': args['references']['comparison']['sha256'] = '0'*64
                elif mutation == 'blocker': comp['rows'][0]['prepared_blocking_reasons']['candidate'] = []
                elif mutation == 'fakeblockedmetric': comp['rows'][0]['candidate']['metrics'] = deepcopy(comp['rows'][-1]['candidate']['metrics'])
                else: del comp['nav_modes_preserved']['modes']['STRICT_SAME_SESSION_FX']
                with self.assertRaises(ValueError): subject.build_tables(**args)

    def test_target_and_risk_rows_are_original_values_with_missing_slots(self):
        args = deepcopy(self.original)
        result = subject.build_tables(**args)
        tables = {item['name']: item['rows'] for item in result['tables']}
        target_rows = tables['候选原目标证券']
        self.assertEqual(sum(row[4] == '原目标未提供' for row in target_rows), 24)
        original = args['candidate_inputs_document']['inputs']['rows'][4]['original_targets_schedule'][0]['targets']
        projected = {row[5]: row for row in target_rows if row[0] == 4}
        self.assertEqual(set(original), set(projected))
        for sid, target in original.items():
            self.assertEqual(projected[sid][6:9], [target['ticker'], target['issuer_id'], subject.encoded(target['target_weight'])])
        self.assertEqual(len(tables['已保存决策风险']), 192)
        self.assertEqual(sum(row[6] == '已保存决策风险' for row in tables['已保存决策风险']), 69)
        self.assertEqual(sum(row[6] == '原决策未保存风险数值' for row in tables['已保存决策风险']), 75)
        original_risk = args['comparison_document']['comparison']['rows'][9]['candidate']['saved_execution_diagnostics']['decisions'][0]
        sid_rows = {row[6]: row for row in tables['决策逐SID原暴露'] if row[0] == 9 and row[4] == '候选' and row[5] == '2026-03-31'}
        for sid, weight in original_risk['decision_risk']['actual_weights'].items():
            self.assertEqual(sid_rows[sid][7:10], [subject.encoded(weight), original_risk['risk_chains'][sid], original_risk['risk_chain_observation_dates'][sid]])
        self.assertFalse(result['full_h_delivery_complete'])
        self.assertEqual(len(result['remaining_delivery_gaps']), 5)


if __name__ == '__main__':
    unittest.main()
